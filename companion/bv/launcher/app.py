"""Barrens Voice launcher: a window instead of the companion's console.

It finds the installed games, keeps the addon in them up to date, starts the companion (a child
process without a console: bv.launcher.process) and shows what it does - the state from its
tmp/state.json, its log lines from its output - and starts the game through Battle.net. Closing the
window hides it by the clock (tray); «Выход» there ends the companion too. Started with --tray (at
Windows sign-in) it waits there for the game and starts the companion when the game appears.

Run: pythonw BarrensVoice.pyw  (or python -m bv.launcher)
"""
from __future__ import annotations

import collections
import os
import queue
import sys
import threading
import time
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

from . import model
from ..paths import DATA_DIR
from .model import APP_DIR, GAME_NAMES
from .paint import DIM, GOLD, PARCHMENT, Painter, ScaledCanvas, register_font, window_icon
from ..logs import parse
from .process import Companion
from .tray import Tray

W = 840
LX0, LX1, RX0, RX1 = 22, 462, 478, W - 22       # left column (state, log), right column (start, game)
TOP, GAP, ROW1 = 100, 14, 140                   # State and Start: one height
MAIN_LEVELS = ("INFO", "WARN", "ERROR")          # the main window's log: how things go, not every detail
MAIN_COLORS = {"WARN": "#e0b33a", "ERROR": "#ff6a5a"}
# hints on the main window's checks and links (what the window does not show by itself)
TIPS = {
    "launch_wow": "Открыли Barrens Voice ярлыком — он сразу запускает игру через Battle.net и уходит в трей. "
                  "При входе в Windows игра сама не запускается.",
    "exit_with_wow": "Игра закрылась — озвучка выключается и освобождает память (если Barrens Voice запущен при входе "
                     "в Windows, он остаётся ждать игру в трее). Выключено — озвучка остаётся включённой до следующей "
                     "игры, голоса рас занимают видеопамять.",
    "autostart": "Barrens Voice запускается при входе в Windows и ждёт в трее (значок у часов). Озвучка включается "
                 "сама, когда вы запустите игру; до этого ничего не загружается и видеопамять свободна.",
    "install": "Скопировать аддон Barrens Voice в папку игры (Interface\\AddOns\\BarrensVoice). "
               "Если игра запущена — потом /reload.",
    "update": "Заменить аддон в игре версией, которая пришла с Barrens Voice. Ваши настройки аддона сохранятся. "
              "Если игра запущена — потом /reload.",
}
SHOW_FILE = DATA_DIR / "tmp" / "launcher.show"   # a second launcher asks the first to show itself
LAUNCHER_LOG = DATA_DIR / "logs" / "launcher.log"
TICK_MS = 400
UPDATE_EVERY = 6 * 3600


def launcher_log(message: str) -> None:
    try:
        LAUNCHER_LOG.parent.mkdir(exist_ok=True)
        if LAUNCHER_LOG.exists() and LAUNCHER_LOG.stat().st_size > 1_000_000:
            LAUNCHER_LOG.replace(LAUNCHER_LOG.with_suffix(".log.1"))
        with open(LAUNCHER_LOG, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {message}\n")
    except OSError:
        pass


class App:
    def __init__(self, root: tk.Tk, args: dict, scale: float = 1.0):
        self.root, self.args, self.scale = root, args, scale
        self.resident = resident = args["tray"]
        self.title_font = register_font()
        root.title("Barrens Voice")
        root.resizable(False, False)
        window_icon(root)
        self.canvas = ScaledCanvas(root, scale, width=W, height=560, highlightthickness=0, bg="#0b0705")
        self.canvas.pack()
        self.p = Painter(self.canvas, self.title_font)

        self.config = model.read_config()
        self.version = model.app_version()
        self.games = model.find_games(self.config)
        keys = [g.key for g in self.games]
        self.selected = self.config.get("game") if self.config.get("game") in keys else (keys[0] if keys else None)
        if args["game"] in keys:                   # --retail / --forever, as the companion takes them
            self.selected = args["game"]
        self.autostart = model.autostart()

        # (time, level, message): every line of the companion and the launcher (bv/logs.py); the main window
        # shows MAIN_LEVELS of them, the log window all
        self.lines: collections.deque[tuple[str, str, str]] = collections.deque(maxlen=20000)
        self.incoming: queue.Queue[str] = queue.Queue()
        self.log_window = None
        self.events: queue.Queue[str] = queue.Queue()
        self.companion = Companion(APP_DIR, self.incoming.put)
        self.companion_game: str | None = None
        self.exit_seen = True            # the companion's end handled (or it never ran)
        self.busy = ""                   # "stopping", "restarting": a stop is on its way
        self.last_code: int | None = None   # how the companion last ended
        self.running_game: str | None = None
        self.extra = args["companion"]   # the companion's own switches given to the launcher (--f5 ...)
        self.update: dict | None = None
        self.drawn = None
        self.settings_win = self.help_win = None
        self.tray = Tray(self.events)
        self.has_tray = self.tray.start()
        self.checked = {"game": 0.0, "games": 0.0, "update": 0.0}
        self.closed = False              # quit() ran: the window is destroyed
        self.reload_told = False         # the /reload hint of this companion's run shown

        root.protocol("WM_DELETE_WINDOW", self.close)
        self.say(f"Barrens Voice {self.version}" + (", ждёт игру в трее" if resident else ""))
        self.redraw()
        if resident and self.has_tray:
            root.withdraw()
        else:
            from .. import launch
            if sys.platform == "win32":
                self.running_game = launch.running_game()[0]
            # the companion (and the race voices in video memory) only with the game: started now when it
            # runs or the launcher starts it; else when it appears (tick) or on «Играть»
            if self.running_game or self.config.get("launch_wow"):
                self.start_companion()
            else:
                self.say("ждёт игру: «Играть» или запуск из Battle.net")
            if self.config.get("launch_wow") and self.companion.running and not self.running_game:
                self.hide(told="Barrens Voice запускает игру и ждёт её в трее — щёлкните значок, чтобы открыть окно.")
        if args["open"]:                           # --open settings|help: straight to that window
            root.after(300, {"settings": self.open_settings, "help": self.open_help, "log": self.open_log}.get(args["open"], lambda: None))
        root.after(TICK_MS, self.tick)

    # --- the companion --------------------------------------------------------------------------

    def say(self, message: str, level: str = "INFO") -> None:
        """A line of the launcher's own in the logs (and its log file)."""
        self.incoming.put(f"{datetime.now():%H:%M:%S} {level:<5} [лаунчер] {message}")
        launcher_log(message)

    def game(self, key: str | None):
        return next((g for g in self.games if g.key == key), None)

    def addon_missing(self) -> bool:
        g = self.game(self.selected)
        return g is not None and g.addon is None

    def start_companion(self, args: list[str] | None = None) -> bool:
        if self.companion.running or self.busy:
            return False
        if self.selected is None:
            self.say("игра не найдена: укажите её папку в «Настройках»", "WARN")
            return False
        if self.addon_missing():
            self.say(f"в {GAME_NAMES[self.selected]} нет аддона — нажмите «установить аддон» в блоке «Игра»", "WARN")
            return False
        if self.config.get("game") != self.selected:
            self.config = model.update_config(game=self.selected)
        self.companion_game = self.selected
        self.exit_seen = False
        self.reload_told = False
        launch_flags = {"--launch", "--no-launch"}
        extra = [a for a in self.extra if not (launch_flags & set(args or []) and a in launch_flags)]
        self.companion.start(extra + list(args or []))
        self.say(f"компаньон запущен ({GAME_NAMES[self.selected]})")
        return True

    def stop_companion(self, then=None, why="stopping") -> None:
        """Stop the companion on a thread (it takes up to a few seconds), then `then` on the window's."""
        if not self.companion.running:
            if then:
                then()
            return
        self.busy = why

        def work():
            self.companion.stop()
            self.events.put(("stopped", then))
        threading.Thread(target=work, daemon=True, name="companion-stop").start()

    def restart_companion(self, args: list[str] | None = None) -> None:
        self.say("перезапускаю компаньон")
        self.stop_companion(lambda: self.start_companion(args), why="restarting")

    def companion_ended(self, code: int | None) -> None:
        self.exit_seen = True
        self.last_code = code
        g = self.game(self.companion_game)
        if g is not None and g.addon is not None:      # killed or crashed hard: it could not say so itself
            from ..status import write
            write(g.addon_dir, stopped=True)
        if code not in (0, None, Companion.RESTART) and self.running_game:
            self.tray.notify("Озвучка чата остановилась (подробности — в журнале). «Включить озвучку» в окне "
                             "запустит её снова; скрытый чат в игре вернёт /reload.")
        state = self.companion.state()
        if Companion.wants_restart(code):
            self.say("компаньону нужна сеть для моделей — запускаю снова")
            self.start_companion()
            return
        if state.get("phase") == "game_closed":
            if self.config.get("exit_with_wow") and not self.resident:
                self.say("игра закрыта — закрываюсь")
                self.quit()
            return
        if code not in (0, None):
            self.say(f"компаньон остановился (код {code}) — подробности в «Журнале»", "ERROR")

    # --- actions --------------------------------------------------------------------------------

    def play(self) -> None:
        if self.busy:
            return
        if self.running_game:                      # the game runs, the companion not (it stopped): voices back on
            if not self.companion.running:
                self.start_companion(["--no-launch"])
            return
        g = self.game(self.selected)
        if g is None:
            self.say("игра не найдена: укажите её папку в «Настройках»", "WARN")
            return
        if g.addon is None and not self.install_addon(g, ask=True):
            return
        if self.companion.running and self.companion_game == self.selected:
            from .. import launch
            launch.launch(dict(self.config, game=self.selected), self.say)
        elif self.companion.running:
            self.restart_companion(["--launch"])
        else:
            self.start_companion(["--launch"])

    def choose_game(self, key: str) -> None:
        if key == self.selected:
            return
        self.selected = key
        self.config = model.update_config(game=key)
        if self.companion.running and self.companion_game != key:
            self.restart_companion(["--no-launch"])
        self.redraw()

    def install_addon(self, g, ask=False) -> bool:
        source = model.addon_source()
        if source is None:
            self.say("аддона нет рядом с программой (папка addon\\BarrensVoice) — установите его вручную", "WARN")
            return False
        if ask and not messagebox.askyesno("Barrens Voice", f"В {g.name} нет аддона Barrens Voice. Установить его?",
                                           parent=self.root):
            return False
        try:
            model.install_addon(source, g.root)
        except OSError as e:
            self.say(f"аддон не установлен: {e}", "WARN")
            return False
        self.say(f"аддон {self.version} установлен в {g.name}" + (" — в игре нужен /reload" if self.running_game == g.key else ""))
        self.games = model.find_games(self.config)
        self.redraw()
        return True

    def toggle(self, key: str) -> None:
        if key == "autostart":
            try:
                model.set_autostart(not self.autostart)
                self.autostart = model.autostart()
            except OSError as e:
                self.say(f"не удалось изменить автозапуск: {e}", "WARN")
        else:
            self.config = model.update_config(**{key: not self.config.get(key)})
            if self.companion.running:
                self.say("изменение подействует при следующем запуске компаньона")
        self.redraw()

    def open_log(self) -> None:
        """The full log in a window of its own, live (logwindow.py)."""
        if self.log_window is not None:
            self.log_window.lift()
            return
        from .logwindow import LogWindow
        self.log_window = LogWindow(self.root, self.lines, self.scale, DATA_DIR / "logs",
                                    on_close=lambda: setattr(self, "log_window", None), header=self.report_header)

    def report_header(self) -> str:
        return model.report_header(self.version, self.companion.state(), model.read_config(), self.games,
                                   self.running_game, running=self.companion.running)

    def dismiss_update(self) -> None:
        if self.update:
            self.config = model.update_config(launcher_dismissed=self.update["version"])
        self.redraw()

    def close(self) -> None:
        """The window's cross: Barrens Voice ends, the companion with it (waiting in the tray is for the
        start with Windows and for the game started automatically)."""
        if self.resident and self.has_tray:
            self.hide()
            return
        if (self.running_game and self.companion.running and not messagebox.askyesno(
                "Barrens Voice", "Игра запущена — озвучка чата остановится. Закрыть Barrens Voice?", parent=self.root)):
            return
        self.quit()

    def hide(self, told: str = "") -> None:
        if not self.has_tray:
            self.quit()
            return
        self.root.withdraw()
        if told or not self.config.get("launcher_tray_told"):
            self.tray.notify(told or "Barrens Voice работает в трее: щёлкните значок, чтобы открыть окно. "
                                     "Выйти — правой кнопкой по значку.")
            if not self.config.get("launcher_tray_told"):
                self.config = model.update_config(launcher_tray_told=True)

    def show(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def quit(self) -> None:
        self.closed = True               # quit may come from inside a tick: nothing is drawn after it
        self.root.withdraw()
        self.tray.stop()
        if self.companion.running:
            self.companion.stop()
        self.root.destroy()

    # --- the loop -------------------------------------------------------------------------------

    def tick(self) -> None:
        if self.closed:
            return
        try:
            self._tick()
        except Exception as e:  # noqa: BLE001 - the window must live on; the error goes to the file
            if self.closed:              # the window went away during this tick: nothing to report
                return
            import traceback
            launcher_log("ошибка: " + "".join(traceback.format_exception(e)))
        if not self.closed:
            self.root.after(TICK_MS, self.tick)

    def _tick(self) -> None:
        now = time.monotonic()
        new = []
        while not self.incoming.empty():
            new.append(parse(self.incoming.get_nowait()))
        self.lines.extend(new)
        if new and self.log_window is not None:
            self.log_window.append(new)
        while not self.events.empty():
            event = self.events.get_nowait()
            if isinstance(event, tuple) and event[0] == "stopped":
                self.busy = ""
                self.exit_seen = True
                if event[1]:
                    event[1]()
            elif event == "show":
                self.show()
            elif event == "play":
                self.play()
            elif event == "quit":
                self.quit()
                return
        if SHOW_FILE.exists():
            SHOW_FILE.unlink(missing_ok=True)
            self.show()
        if now - self.checked["game"] > 2:
            self.checked["game"] = now
            from .. import launch
            self.running_game, folder = launch.running_game() if sys.platform == "win32" else (None, None)
            changes = model.remember(self.config, self.running_game, folder) if folder else None
            if changes:                                # where the game is, for next time and the companion
                self.config = model.update_config(**changes)
                self.games = model.find_games(self.config)
            if self.running_game and self.running_game != self.selected and not self.companion.running:
                self.selected = self.running_game      # the game the player started: that one
        if now - self.checked["games"] > 15:
            self.checked["games"] = now
            self.games = model.find_games(self.config)
        if now - self.checked["update"] > UPDATE_EVERY:
            self.checked["update"] = now
            threading.Thread(target=self._check_update, daemon=True, name="update-check").start()
        if self.companion.running and not self.reload_told and self.companion.state().get("reload_hint"):
            self.reload_told = True          # started after the player entered the world: say it outside the game too
            self.tray.notify("Озвучка включена. Если окно чата не прячется — сделайте в игре /reload: аддон узнаёт "
                             "о Barrens Voice при входе в игру и /reload.")
        if not self.exit_seen and not self.busy and not self.companion.running:
            self.companion_ended(self.companion.poll())
        # the game started from Battle.net while the companion is not running (waiting in the tray, or
        # after the last game was closed): start it for that game - unless it ended with an error
        if (self.running_game and not self.companion.running and not self.busy and self.exit_seen
                and self.last_code in (0, None) and self.game(self.running_game) and not self.addon_missing()):
            self.selected = self.running_game
            self.start_companion(["--no-launch"])
        self.redraw()

    def _check_update(self) -> None:
        found = model.latest_release()
        if found and model.newer(found["version"], self.version):
            self.update = found
            launcher_log(f"вышла версия {found['version']}")

    # --- drawing --------------------------------------------------------------------------------

    def snapshot(self):
        state = self.companion.state()
        lines = model.describe(state, self.companion.running, self.companion.poll(),
                               GAME_NAMES.get(self.running_game) if self.running_game else None,
                               self.addon_missing() and not self.companion.running)
        if self.busy:
            lines[0] = (model.YELLOW, "Компаньон перезапускается…" if self.busy == "restarting" else "Компаньон останавливается…")
        show_update = bool(self.update) and self.config.get("launcher_dismissed") != self.update["version"]
        games = tuple((g.key, g.addon, str(g.root)) for g in self.games)
        progress = tuple(item for item in list(self.lines)[-400:] if item[1] in MAIN_LEVELS)[-14:]
        return (tuple(lines), progress, games, self.selected, self.running_game, show_update,
                self.companion.running,
                self.config.get("launch_wow"), self.config.get("exit_with_wow"), self.autostart)

    def redraw(self) -> None:
        if self.closed:
            return
        snap = self.snapshot()
        if snap == self.drawn:
            return
        self.drawn = snap
        lines, log, _, _, _, show_update, _, launch_wow, exit_with_wow, autostart = snap
        c, p = self.canvas, self.p
        c.delete("all")
        n = max(1, len(self.games))
        row2 = 36 + n * 56 + 40                    # Game: its cards and the note; the log as tall
        y2 = TOP + ROW1 + GAP
        y3 = y2 + row2 + GAP
        bottom = y3 + 52 + (GAP + 48 if show_update else 0)
        h = bottom + 30
        c.config(height=h)
        p.background(W, h)
        p.title(W, "Barrens Voice", "озвучка чата голосами рас")

        # row 1: State | Start
        p.panel(LX0, TOP, LX1, TOP + ROW1, "Состояние")
        for i, (color, text) in enumerate(lines):
            yy = TOP + 48 + i * 24
            c.create_oval(LX0 + 16, yy - 5, LX0 + 26, yy + 5, fill=color, outline="")
            c.create_text(LX0 + 36, yy, text=p.fit(text, p.body, LX1 - LX0 - 50), anchor="w", fill=PARCHMENT, font=p.body)
        p.panel(RX0, TOP, RX1, TOP + ROW1, "Запуск")
        for i, (key, text, on) in enumerate((("launch_wow", "Запускать игру вместе с Barrens Voice", launch_wow),
                                             ("exit_with_wow", "Закрываться вместе с игрой", exit_with_wow),
                                             ("autostart", "Запускать при входе в Windows", autostart))):
            p.check(RX0 + 14, TOP + 48 + i * 24, text, bool(on), f"check{i}", lambda k=key: self.toggle(k), tip=TIPS[key])

        # row 2: the log | Game
        p.panel(LX0, y2, LX1, y2 + row2, "Журнал")
        fits = (row2 - 44 - 6) // 18 + 1
        for i, (time, level, message) in enumerate(log[-fits:]):      # the level itself is not shown here
            c.create_text(LX0 + 14, y2 + 44 + i * 18, text=p.fit(f"{time} {message}", p.mono, LX1 - LX0 - 28),
                          anchor="w", fill=MAIN_COLORS.get(level, "#c9b896"), font=p.mono)
        p.panel(RX0, y2, RX1, y2 + row2, "Игра")
        if not self.games:
            c.create_text(RX0 + 14, y2 + 40, anchor="nw", width=RX1 - RX0 - 28, fill=PARCHMENT, font=p.body,
                          text="WoW Forever и WoW Retail не найдены. Укажите папку игры в «Настройках».")
        for i, g in enumerate(self.games):
            y0 = y2 + 36 + i * 56
            on = g.key == self.selected
            tag = f"game{i}"
            p.rounded(RX0 + 14, y0, RX1 - 14, y0 + 48, r=7, fill="#46300f" if on else "#281a0e",
                      outline=GOLD if on else "#5a4220", width=2 if on else 1, tags=(tag, tag + "box"))
            if not on:
                p.hover(tag, lambda t=tag: c.itemconfig(t + "box", outline="#c9a24a"),
                        lambda t=tag: c.itemconfig(t + "box", outline="#5a4220"))
            title = g.name + ("  •  запущена" if g.key == self.running_game else "")
            c.create_text(RX0 + 26, y0 + 15, text=title, anchor="w", fill=PARCHMENT, font=p.body, tags=tag)
            c.create_text(RX0 + 26, y0 + 34, text=p.fit(str(g.root), p.small, 200), anchor="w", fill=DIM,
                          font=p.small, tags=tag)
            p.click(tag, lambda k=g.key: self.choose_game(k))
            if g.addon is None:
                p.link(RX1 - 26, y0 + 15, "установить аддон", f"inst{i}", lambda g=g: self.install_addon(g), anchor="e",
                       tip=TIPS["install"])
            elif model.newer(self.version, g.addon):
                p.link(RX1 - 26, y0 + 15, f"обновить аддон {g.addon} → {self.version}", f"inst{i}",
                       lambda g=g: self.install_addon(g), anchor="e", tip=TIPS["update"])
            else:
                c.create_text(RX1 - 26, y0 + 15, text=f"аддон {g.addon}", anchor="e", fill=DIM, font=p.small, tags=tag)
        c.create_text(RX0 + 14, y2 + 36 + n * 56, anchor="nw", width=RX1 - RX0 - 28, fill=DIM, font=p.small,
                      text="Запустили игру сами из Battle.net — компаньон подхватит её сам.")

        # row 3: the buttons under the log | Play under Game
        bw = (LX1 - LX0 - 2 * 10) / 3
        for i, (text, action) in enumerate((("Журнал", self.open_log), ("Настройки", self.open_settings),
                                            ("Помощь", self.open_help))):
            x0 = LX0 + i * (bw + 10)
            p.button(x0, y3 + 8, x0 + bw, y3 + 44, text, f"small{i}", action)
        playing, voiced = bool(self.running_game), self.companion.running
        label = "Играть" if not playing else "Игра запущена" if voiced else "Включить озвучку"
        p.big_button(RX0, y3, RX1, y3 + 52, label, "play", self.play,
                     enabled=not self.busy and not (playing and voiced))

        # the update, across the whole window
        if show_update:
            y = y3 + 52 + GAP
            u = self.update
            p.rounded(22, y, W - 22, y + 48, r=6, fill="#3c2d0a", outline="#b8862b")
            c.create_text(36, y + 24, text=f"Вышла версия {u['version']}", anchor="w", fill=GOLD, font=(self.title_font, -18))
            c.create_text(200, y + 24, text="— аддон и компаньон", anchor="w", fill=PARCHMENT, font=p.body)
            p.button(W - 236, y + 9, W - 136, y + 39, "Что нового", "news", lambda: webbrowser.open(u["url"]))
            p.button(W - 128, y + 9, W - 58, y + 39, "Обновить", "update", lambda: webbrowser.open(u["url"]))
            p.button(W - 50, y + 9, W - 30, y + 39, "×", "dismiss", self.dismiss_update)
        c.create_text(W - 24, h - 16, text=f"версия {self.version}", anchor="e", fill=DIM, font=p.small)
        self.tray.tooltip("Barrens Voice — " + lines[0][1])

    # --- settings and help ----------------------------------------------------------------------

    def _child(self, title: str, width: int, height: int):
        win = tk.Toplevel(self.root)
        win.title(f"Barrens Voice — {title}")
        win.resizable(False, False)
        win.transient(self.root)
        if self.root.winfo_viewable():           # over the main window, not in the screen's corner
            win.geometry(f"+{self.root.winfo_rootx() + 60}+{self.root.winfo_rooty() + 40}")
        canvas = ScaledCanvas(win, self.scale, width=width, height=height, highlightthickness=0, bg="#0b0705")
        canvas.pack()
        p = Painter(canvas, self.title_font)
        p.background(width, height)
        p.title(width, title, size=30, y=36)
        return win, canvas, p

    def open_settings(self) -> None:
        if self.settings_win is not None and self.settings_win.winfo_exists():
            self.settings_win.lift()
            return
        width, height = 600, 580
        win, c, p = self._child("Настройки", width, height)
        self.settings_win = win
        cfg = model.read_config()
        boxes = {}
        rows = (("wow_dir", "Папка игры (…\\_forever_ или …\\_retail_), если её не нашли сами", "dir"),
                ("battlenet_exe", "Battle.net.exe, если его не нашли сами", "exe"),
                ("hf_home", "Папка кэша моделей (пусто — папка hf рядом с программой)", "dir"),
                ("log_keep_days", "Сколько дней хранить журналы (0 — всегда)", ""))
        y = 80
        for key, label, pick in rows:
            c.create_text(30, y, text=label, anchor="w", fill=PARCHMENT, font=p.body)
            boxes[key] = p.entry(30, y + 26, width - 60 - (100 if pick else 0), str(cfg.get(key, "")))
            if pick:
                def choose(k=key, kind=pick):
                    got = (filedialog.askdirectory(parent=win) if kind == "dir"
                           else filedialog.askopenfilename(parent=win, filetypes=[("Battle.net", "Battle.net.exe")]))
                    if got:
                        boxes[k].var.set(os.path.normpath(got))
                p.button(width - 120, y + 13, width - 30, y + 39, "Выбрать…", f"pick{key}", choose)
            y += 66
        flags = {"details": bool(cfg.get("log_details")), "whisper": cfg.get("f5_end_check") == "whisper"}

        def draw_check(key, y, label):
            c.delete(key)
            p.check(30, y, label, flags[key], key,
                    lambda: (flags.__setitem__(key, not flags[key]), draw_check(key, y, label)))
        draw_check("details", y + 6, "Подробный журнал: как строка написана и как прочитана")
        draw_check("whisper", y + 44, "Проверять концовки фраз распознаванием речи (Whisper)")
        c.create_text(56, y + 64, anchor="nw", fill=DIM, font=p.small, width=width - 86,
                      text="Изредка голос расы не успевает договорить последний слог. Выключено: фраза, "
                           "договорённая впритык (примерно каждая восьмая), синтезируется ещё раз — на секунду "
                           "дольше. Включено: Whisper сначала слушает её конец и переделывает только при обрыве, "
                           "но занимает около 1,5 ГБ видеопамяти и пару секунд при загрузке голосов.")
        c.create_text(30, y + 150, anchor="w", fill=DIM, font=p.small,
                      text="Остальное — в config.json (описание в README). Компаньон перезапустится, если он работает.")

        def edited():
            """The settings as the window has them now; None if the days are not a number."""
            try:
                days = int(boxes["log_keep_days"].var.get() or 0)
            except ValueError:
                return None
            changes = {k: boxes[k].var.get().strip() for k in ("wow_dir", "battlenet_exe", "hf_home")}
            changes.update(log_keep_days=days, log_details=flags["details"],
                           f5_end_check="whisper" if flags["whisper"] else "silence")
            return changes

        def differs(changes: dict) -> bool:
            """Whether `changes` differ from the file: an empty field is the same as a key not set."""
            unset = {"f5_end_check": "silence", "log_details": True, "log_keep_days": 90}
            return any((cfg.get(k) if cfg.get(k) is not None else unset.get(k, "")) != v for k, v in changes.items())

        def save():
            changes = edited()
            if changes is None:
                messagebox.showerror("Barrens Voice", "Дни хранения журналов — целое число.", parent=win)
                return
            changed = differs(changes)
            self.config = model.update_config(**changes)
            self.games = model.find_games(self.config)
            win.destroy()
            if changed:
                self.say("настройки сохранены")
                if self.companion.running:
                    self.restart_companion(["--no-launch"])
            self.redraw()

        def open_file():
            try:
                os.startfile(model.CONFIG_PATH)     # noqa: S606
            except (OSError, AttributeError) as e:
                self.say(f"не открылся config.json: {e}", "WARN")
        p.button(30, height - 60, 170, height - 26, "Сохранить", "save", save)
        p.button(182, height - 60, 362, height - 26, "Открыть config.json", "file", open_file)
        def close():
            """The cross and «Закрыть»: changes not saved are asked about, not lost silently."""
            changes = edited()
            if changes is None or differs(changes):
                answer = messagebox.askyesnocancel("Barrens Voice", "Сохранить изменения в настройках?", parent=win)
                if answer is None:
                    return
                if answer:
                    save()
                    return
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", close)
        p.button(width - 150, height - 60, width - 30, height - 26, "Закрыть", "close", close)

    def open_help(self) -> None:
        if self.help_win is not None and self.help_win.winfo_exists():
            self.help_win.lift()
            return
        from ..links import LINKS
        width, height = 760, 396
        win, c, p = self._child("Помощь", width, height)
        self.help_win = win
        win.icons = []
        media = model.addon_source()
        try:
            from PIL import Image, ImageTk
        except ImportError:
            Image = ImageTk = None

        def picture(name: str, size: int):
            """A picture from the addon's Media (the same as in the game), or None."""
            if Image is None or media is None:
                return None
            try:
                img = ImageTk.PhotoImage(Image.open(media / "Media" / f"{name}.tga").resize((round(size * self.scale),) * 2),
                                         master=win)
            except OSError:
                return None
            win.icons.append(img)
            return img

        # three blocks a gap apart: what this is for, the links, what to send
        c.create_text(30, 78, anchor="nw", fill=PARCHMENT, font=p.body,
                      text="Ошибки, улучшения, предложения, или что-то прочитано неправильно — пишите в Discord или Telegram.")
        github = "Или сразу заведите issue на GitHub"
        c.create_text(30, 116, anchor="nw", fill=PARCHMENT, font=p.body, text=github)
        smile = picture("smile", 16)
        if smile:
            c.create_image(30 + p.measure(github, p.body) + 6, 116 + 9, image=smile)
        for i, (key, name) in enumerate((("discord", "Discord"), ("telegram", "Telegram"), ("github", "GitHub"))):
            y = 168 + i * 44
            x = 30
            img = picture(key, 22)
            if img:
                c.create_image(x + 11, y, image=img)
            c.create_text(x + 32, y, text=name, anchor="w", fill=GOLD, font=p.body)
            box = p.entry(x + 120, y, 410, LINKS[key], readonly=True)
            box.bind("<FocusIn>", lambda e, b=box: b.select_range(0, "end"))

            def copy(url=LINKS[key]):
                win.clipboard_clear()
                win.clipboard_append(url)
                self.say("ссылка скопирована")
            p.button(x + 540, y - 14, x + 630, y + 14, "Копировать", f"copy{key}", copy, font=p.small)
            p.button(x + 638, y - 14, x + 700, y + 14, "Открыть", f"open{key}",
                     lambda url=LINKS[key]: webbrowser.open(url), font=p.small)
        c.create_text(30, 290, anchor="nw", width=width - 60, fill=PARCHMENT, font=p.body,
                      text="Что прислать: что прозвучало и как надо, а лучше — строку из журнала (кнопка «Журнал»). "
                           "Неверное ударение можно сразу поправить себе на вкладке «Словарь» в настройках аддона.")
        p.button(width - 150, height - 50, width - 30, height - 18, "Закрыть", "close", win.destroy)


APP_ID = "BarrensVoice.Launcher"


def register_app_id() -> None:
    """The name and icon Windows shows for the launcher's notifications (else the id itself): a key
    under the user's AppUserModelId, as an installer would write it."""
    try:
        import winreg
        from .paint import ICON_FILE
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\AppUserModelId\{APP_ID}") as key:
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, "Barrens Voice")
            winreg.SetValueEx(key, "IconUri", 0, winreg.REG_SZ, str(ICON_FILE))
    except OSError:
        pass


def single_instance() -> bool:
    """True for the first launcher; a second one asks the first to show itself and ends."""
    if sys.platform != "win32":
        return True
    import ctypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    global _mutex
    _mutex = kernel32.CreateMutexW(None, False, "Local\\BarrensVoiceLauncher")
    if ctypes.get_last_error() == 183:                    # ERROR_ALREADY_EXISTS
        try:
            SHOW_FILE.parent.mkdir(parents=True, exist_ok=True)
            SHOW_FILE.touch()
        except OSError:
            pass
        return False
    return True


_mutex = None


def run_in_console(args: dict) -> None:
    """--console: the companion in a console window of its own, as BarrensVoice.cmd ran it before the
    launcher (the window stays open after an error, to read it)."""
    import subprocess
    python = Path(sys.executable).with_name("python.exe")
    flags = ([f"--{args['game']}"] if args["game"] else []) + args["companion"]
    command = subprocess.list2cmdline([str(python), "-m", "bv", *flags])
    subprocess.Popen(f'cmd.exe /c "title Barrens Voice & {command} || pause"', cwd=APP_DIR,
                     creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))


def main() -> int:
    if sys.stderr is None or "pythonw" in Path(sys.executable).name.lower():
        LAUNCHER_LOG.parent.mkdir(exist_ok=True)
        sys.stderr = open(LAUNCHER_LOG, "a", encoding="utf-8", buffering=1)   # tracebacks of a windowless run
        sys.stdout = sys.stderr
    args = model.parse_args(sys.argv[1:])
    if args["help"] or args["unknown"]:
        root = tk.Tk()
        root.withdraw()
        text = (f"Неизвестно: {' '.join(args['unknown'])}\n\n" if args["unknown"] else "") + model.USAGE
        messagebox.showinfo("Barrens Voice", text, parent=root)
        return 0 if args["help"] else 2
    if args["console"]:
        run_in_console(args)
        return 0
    if not single_instance():
        return 0
    if sys.platform == "win32":
        import ctypes
        try:                                           # sharp at any screen scale; ScaledCanvas does the sizes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()
        register_app_id()                              # its own taskbar button and icon, not Python's
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    root = tk.Tk()
    scale = args["scale"] or max(1.0, root.winfo_fpixels("1i") / 96)
    if args["pos"]:
        root.geometry("+{}+{}".format(*args["pos"].split(",")))
    App(root, args, scale)
    root.mainloop()
    return 0
