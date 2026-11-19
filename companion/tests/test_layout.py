"""The launcher's windows in every state they draw, checked for text running over text, over a button that is
not its own, or out of its panel or window. Drawn on a hidden Tk window: Tk measures the text as on the
screen (on Windows - the fonts the players have; elsewhere their stand-ins, so CI on Windows is the check
that counts). Skipped where Tk has no display.

Run alone, it also writes what failed: `python -m unittest test_layout` from companion/tests.
"""
from __future__ import annotations

import itertools
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    import tkinter as tk
    _root = tk.Tk()
    _root.withdraw()
except Exception:  # noqa: BLE001 - no display (a headless Linux box): nothing to measure
    _root = None

PANEL_FILL = "#160f09"   # paint.Painter.panel's fill: a text that starts in a panel ends in it
TOLERANCE = 1            # pixels two boxes may share (antialiasing, rounding at a scale)
BUTTON_HEIGHT = 44       # a tagged box lower than this is a button (game cards are 48, panels more)


def problems(c: "tk.Canvas") -> list[str]:
    """What runs over what on this canvas, in words."""
    c.update_idletasks()
    width, height = int(float(c.cget("width"))), int(float(c.cget("height")))
    items = []
    for i in c.find_all():
        box = c.bbox(i)
        if not box:
            continue
        kind, tags = c.type(i), c.gettags(i)
        items.append(SimpleNamespace(id=i, kind=kind, box=box, group=tags[0] if tags else None, tags=tags,
                                     text=c.itemcget(i, "text") if kind == "text" else "",
                                     fill=c.itemcget(i, "fill") if kind in ("polygon", "rectangle") else ""))
    texts = [t for t in items if t.kind == "text" and t.text.strip()]
    buttons = [b for b in items if b.kind == "polygon" and any(t.endswith("box") for t in b.tags)
               and b.box[3] - b.box[1] < BUTTON_HEIGHT]
    panels = [p for p in items if p.kind == "polygon" and not p.tags and p.fill == PANEL_FILL]

    def meet(a, b) -> bool:
        return (min(a[2], b[2]) - max(a[0], b[0]) > TOLERANCE) and (min(a[3], b[3]) - max(a[1], b[1]) > TOLERANCE)

    def inside(a, b) -> bool:
        return a[0] >= b[0] - TOLERANCE and a[1] >= b[1] - TOLERANCE and a[2] <= b[2] + TOLERANCE and a[3] <= b[3] + TOLERANCE

    out = []
    for a, b in itertools.combinations(texts, 2):
        if a.text != b.text and meet(a.box, b.box):          # the same text twice: a title over its shadow
            out.append(f"«{a.text}» и «{b.text}» наложились")
    for t in texts:
        for b in buttons:
            if b.group != t.group and meet(t.box, b.box):
                out.append(f"«{t.text}» залезает на кнопку {b.group}")
        x0, y0, x1, y1 = t.box
        if x0 < -TOLERANCE or y0 < -TOLERANCE or x1 > width + TOLERANCE or y1 > height + TOLERANCE:
            out.append(f"«{t.text}» за краем окна ({x0},{y0})-({x1},{y1}), окно {width}×{height}")
        for p in panels:
            px0, py0, px1, py1 = p.box
            if px0 <= x0 <= px1 and py0 <= (y0 + y1) / 2 <= py1 and x1 > px1 + TOLERANCE:
                out.append(f"«{t.text}» вылезает за правый край панели на {x1 - px1} px")
    for t in (i for i in items if i.kind == "window"):        # text boxes (settings) inside the window
        if t.box[2] > width + TOLERANCE or t.box[3] > height + TOLERANCE:
            out.append(f"поле ввода за краем окна: {t.box}")
    return out


class FakeCompanion:
    RESTART, ALREADY, CONFIG_ERROR = 3, 4, 5            # bv.launcher.process.Companion's

    def __init__(self, *_):
        self.running, self.st, self.code = False, {}, None

    def state(self):
        return self.st

    def poll(self):
        return self.code

    @classmethod
    def wants_restart(cls, code):
        return code == cls.RESTART


class FakeTray:
    def __init__(self, *_):
        pass

    def start(self):
        return False

    def notify(self, *_):
        pass

    def tooltip(self, text):
        self.said = text                 # the tray icon's hint (test_main_window_in_every_state)


def game(key, addon, root=None):
    from bv.launcher.model import GAME_NAMES, Game
    return Game(key, GAME_NAMES[key], Path(root or f"E:/World of Warcraft/_{key}_"), addon)


LONG_ROOT = "E:/Games/Blizzard Entertainment/Очень длинная папка/World of Warcraft/_forever_"
GAMES = {
    "none": [],
    "no addon": [game("forever", None)],
    "old addon": [game("forever", "0.2.1", LONG_ROOT), game("retail", "0.3.1")],
    "older and newer": [game("forever", "0.3.0"), game("retail", "0.10.0")],
}
STATES = [   # the companion's state file: every line describe() can say
    ({}, False, None),
    ({"phase": "running", "voices": "bank", "linked": False, "window": False}, True, None),
    ({"phase": "running", "voices": "ready", "device": "NVIDIA GeForce RTX 5070 Ti Laptop GPU", "linked": True}, True, None),
    ({"phase": "running", "voices": "error", "damaged": True}, True, None),
    ({"phase": "running", "voices": "off"}, True, None),
    ({"phase": "error", "error": "очень длинная ошибка " * 8}, False, 1),
    ({"phase": "stopped"}, False, 3),
    ({"phase": "running", "voices": "ready", "mismatch": "newer"}, True, None),
    ({"phase": "running", "voices": "ready", "mismatch": "older"}, True, None),
]
LOG = [("04:45:32", "INFO", "озвучка запускается (WoW Forever)"),
       ("04:45:46", "INFO", "собираю голоса рас: 23 из 66"),
       ("04:46:00", "WARN", "в WoW Forever нет аддона — «установить аддон» справа"),
       ("04:46:01", "ERROR", "очень длинная строка журнала без пробелов " + "x" * 80),
       ("04:46:02", "INFO", "строка " * 30)]
UPDATES = [None,
           {"version": "0.4.0b7", "url": "u"},
           {"version": "0.4.10b12", "url": "u", "addon": "0.10.1"},
           {"version": "0.10.10", "url": "u", "addon": "0.3.1"}]
STATUSES = ["", "downloading", "preparing", "ready", "error"]


@unittest.skipIf(_root is None, "no display for Tk")
class Layout(unittest.TestCase):
    def make(self, scale=1.0, config=None, install=None, problem=None):
        """The window as it opens (a Toplevel of the hidden root); `install`: an install's folder (the updater's
        steps at the start then run on it), `problem`: what config_problem says."""
        from bv.launcher import app, model
        top = tk.Toplevel(_root)
        top.withdraw()
        self.after_calls = []
        real_after = top.after
        top.after = lambda ms, *a: (self.after_calls.append((ms, *a)), real_after(ms, *a))[1]
        patches = [mock.patch.object(app, "Companion", FakeCompanion), mock.patch.object(app, "Tray", FakeTray),
                   mock.patch.object(app, "launcher_log", lambda *_: None),
                   mock.patch.object(app, "window_icon", lambda *_: None),
                   mock.patch.object(model, "read_config", lambda: dict(config or {})),
                   mock.patch.object(model, "update_config", lambda **kw: dict(config or {}, **kw)),
                   mock.patch.object(model, "config_problem", lambda: problem),
                   mock.patch.object(model, "find_games", lambda *a, **k: []),
                   mock.patch.object(model, "autostart", lambda: False),
                   mock.patch.object(model, "app_version", lambda: "0.4.0b7"),
                   mock.patch.object(model, "addon_version", lambda: "0.3.1"),
                   mock.patch.object(app, "INSTALL_DIR", install)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        a = app.App(top, model.parse_args([]), scale)
        a.root.after_cancel = lambda *_: None
        for job in a.root.tk.call("after", "info"):         # no ticks: the test draws, nothing else
            a.root.after_cancel(job)
        self.addCleanup(top.destroy)
        return a

    def check(self, canvas, what: str, found: list):
        for p in problems(canvas):
            found.append((p, what))

    def test_main_window_in_every_state(self):
        found: list[tuple[str, str]] = []
        for scale in (1.0, 1.25, 1.5):
            a = self.make(scale)
            a.lines.extend(LOG)
            a.main.extend(item for item in LOG if item[1] in ('INFO', 'WARN', 'ERROR'))
            for (gname, games), (st, running, code), running_game in itertools.product(
                    GAMES.items(), STATES, (None, "forever")):
                a.games, a.selected = games, games[0].key if games else None
                a.companion.st, a.companion.running, a.companion.code = st, running, code
                a.running_game = running_game if games else None
                for u, status, busy in itertools.product(UPDATES, STATUSES, ("", "stopping")):
                    if u is None and status:
                        continue
                    a.update, a.busy = u, busy
                    a.updater = SimpleNamespace(status=status, ready="x" if status == "ready" else None) if u else None
                    a.config = {"launch_wow": True, "exit_with_wow": True}
                    a.drawn = None
                    a.redraw()
                    self.assertTrue(a.tray.said.startswith("Barrens Voice Launcher — "), a.tray.said)   # the program's name
                    self.check(a.canvas, f"главное окно ×{scale}, игры «{gname}», {st.get('phase')}/{st.get('voices')}, "
                                         f"игра {running_game}, обновление {u and u['version']} {status} {busy}", found)
        self.report(found)

    def test_settings_and_help(self):
        found: list[tuple[str, str]] = []
        for scale in (1.0, 1.25, 1.5):
            for config in ({}, {"game_dirs": {"forever": LONG_ROOT}, "hf_home": "D:/" + "очень/" * 20}):
                a = self.make(scale, config)
                a.games = GAMES["old addon"]
                a.open_settings()
                self.check(a.settings_win.winfo_children()[0], f"настройки ×{scale}", found)
                a.settings_win.destroy()
                a.open_help()
                self.check(a.help_win.winfo_children()[0], f"помощь ×{scale}", found)
                a.help_win.destroy()
        self.report(found)

    def test_a_busy_chat_keeps_the_main_window_filled(self):
        # each chat line brings a CHAT and two DEBUG lines: they pushed the INFO lines out of the window of recent
        # lines, and the main window's log went blank in a busy raid
        import tempfile
        import time
        from bv.launcher import app
        a = self.make()
        with tempfile.TemporaryDirectory() as d, mock.patch.object(app, "SHOW_FILE", Path(d) / "launcher.show"):
            now = time.monotonic()
            a.checked = {"game": now, "games": now, "update": now}      # the tick's checks wait: only the lines
            a.incoming.put("20:13:37 INFO  голоса рас готовы")
            for i in range(a.lines.maxlen // 3 + 10):
                a.incoming.put(f"20:14:00 CHAT  [Громмаш] строка {i}")
                a.incoming.put("20:14:00 DEBUG   исходно: строка")
                a.incoming.put("20:14:00 DEBUG   к синтезу: строка")
            a._tick()
        self.assertNotIn("голоса рас готовы", [m for _, _, m in a.lines])   # gone from the log window's lines
        drawn = [a.canvas.itemcget(i, "text") for i in a.canvas.find_all() if a.canvas.type(i) == "text"]
        self.assertTrue(any("голоса рас готовы" in text for text in drawn), drawn)

    def test_settings_saved_with_what_the_file_did_not_take(self):
        # a change config.json did not take (pending) was lost to the settings window's save
        from bv.launcher import model, paint
        a = self.make()
        a.pending, a.config_told = {"game": "retail"}, {"unwritten"}
        actions, written, real = {}, [], paint.Painter.button

        def button(p, x0, y0, x1, y1, text, tag, action=None, **k):
            actions[tag] = action
            return real(p, x0, y0, x1, y1, text, tag, action, **k)
        with mock.patch.object(paint.Painter, "button", button), \
                mock.patch.object(model, "update_config", lambda **kw: written.append(kw) or kw):
            a.open_settings()
            actions["save"]()
        self.assertEqual(written[0]["game"], "retail")
        self.assertEqual((a.pending, a.config_told), ({}, set()))

    def test_an_installs_start(self):
        # what the window's start does in an install: app\\current made again after a switch cut short, the old
        # versions pruned a few seconds later; a config.json that does not read said once
        import tempfile
        from bv.launcher import app
        from bv.logs import parse
        from bv.paths import CODE_DIR
        with tempfile.TemporaryDirectory() as d, \
                mock.patch("bv.install.repair_current", return_value=True) as repair, \
                mock.patch("bv.install.place_starter"), mock.patch("bv.update.note_version"):
            a = self.make(install=Path(d), problem="config.json не читается")
        repair.assert_called_once_with(Path(d), CODE_DIR.parent)
        lines = [m for _, _, m in (parse(a.incoming.get_nowait()) for _ in range(a.incoming.qsize()))]
        self.assertTrue(any("переход на другую версию в прошлый раз прервался" in m for m in lines), lines)
        self.assertIn((app.PRUNE_AFTER_MS, a.prune_versions), self.after_calls)
        self.assertEqual(a.config_told, {"broken"})
        b = self.make()                                          # run from the source: none of it
        self.assertNotIn(app.PRUNE_AFTER_MS, [c[0] for c in self.after_calls])
        self.assertEqual(b.config_told, set())

    def test_a_fresh_version_settles_while_its_companion_runs(self):
        # settled only when its companion ended by itself: one the launcher always stops («Закрываться вместе с
        # игрой» off, the window closed first) stayed watched for good - nothing pruned, and two failed starts
        # months later still went back
        import tempfile
        from bv import install, update
        from bv.launcher import app
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for v in ("0.3.9", "0.4.0", "0.4.1"):
                folder = root / "app" / v
                for f in install.STARTS:
                    (folder / f).parent.mkdir(parents=True, exist_ok=True)
                    (folder / f).write_bytes(b"")
            install.point_current(root, root / "app" / "0.4.0")
            update.apply(root, "0.4.1")
            with mock.patch("bv.install.repair_current", return_value=False), mock.patch("bv.install.place_starter"), \
                    mock.patch("bv.update.note_version"):
                a = self.make(install=root)
            clock = [1000.0]
            a.checked = {"game": 1e9, "games": 1e9, "update": 1e9}      # the tick's other checks wait
            a.companion.running, a.companion_started, a.settle_due = True, 1000.0, True
            with mock.patch.object(app.time, "monotonic", lambda: clock[0]), \
                    mock.patch.object(app, "SHOW_FILE", root / "launcher.show"):
                clock[0] = 1000.0 + update.EARLY - 1
                a._tick()
                self.assertTrue(update.state_path(root).exists())                       # not yet
                clock[0] = 1000.0 + update.EARLY + 1
                a._tick()
                self.assertFalse(update.state_path(root).exists())                      # settled while it runs
                update.pruning.join(10)
                self.assertEqual(sorted(p.name for p in (root / "app").iterdir()), ["0.4.0", "0.4.1", "current"])
                update.write_json(update.state_path(root), {"version": "0.4.1", "previous": "0.4.0", "fails": 1})
                a._tick()                                                               # once per run
                self.assertTrue(update.state_path(root).exists())
                update.state_path(root).unlink()
                a.companion.running, a.companion.code = False, 1                       # then it crashes: nothing
                a.exit_seen = False
                a._tick()
            self.assertEqual((install.current_version(root), update.refused(root)), ("0.4.1", None))
            self.assertFalse(update.state_path(root).exists())

    def report(self, found: list[tuple[str, str]]):
        """Each problem once, with how often and the first state it was seen in."""
        seen: dict[str, list[str]] = {}
        for problem, what in found:
            seen.setdefault(problem, []).append(what)
        if seen:
            self.fail(f"{len(seen)} наложений:\n" + "\n".join(
                f"- {problem}  [{len(whats)} раз; например: {whats[0]}]" for problem, whats in seen.items()))


if __name__ == "__main__":
    unittest.main()
