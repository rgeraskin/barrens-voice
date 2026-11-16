"""The full log: every line of the companion and the launcher as it comes - synthesis, chat, details -
with the level, filters by level and by text, copying, and scrolling that follows new lines only
while the view is at the bottom (scrolled up to read, it stays where it is)."""
from __future__ import annotations

import os
import tkinter as tk
from datetime import datetime
from pathlib import Path

from .paint import DIM, GOLD, PARCHMENT

LEVELS = (("INFO", "Ход работы"), ("CHAT", "Чат"), ("DEBUG", "Подробности"), ("WARN", "Предупреждения"),
          ("ERROR", "Ошибки"))
COLORS = {"DEBUG": "#8a7a66", "CHAT": "#e8d8b0", "INFO": "#f0dcae", "WARN": "#e0b33a", "ERROR": "#ff6a5a"}
BG, PANEL = "#0d0906", "#1a120b"
KEEP = 20000                       # lines in the view at most: the oldest go first


class LogWindow:
    def __init__(self, root: tk.Tk, lines, scale: float, log_dir: Path, on_close, header=None):
        self.lines, self.log_dir, self.on_close = lines, Path(log_dir), on_close
        self.header = header           # () -> str: versions, card, settings (model.report_header)
        self.win = tk.Toplevel(root, bg=PANEL)
        self.win.title("Barrens Voice — журнал")
        self.win.geometry(f"{round(940 * scale)}x{round(600 * scale)}")
        self.win.minsize(round(560 * scale), round(300 * scale))
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        px = lambda n: round(n * scale)                                   # noqa: E731
        ui = ("Segoe UI", -px(13))
        self.shown = {level: tk.BooleanVar(value=level != "DEBUG") for level, _ in LEVELS}
        self.find = tk.StringVar()

        bar = tk.Frame(self.win, bg=PANEL)
        bar.pack(fill="x", padx=px(10), pady=(px(8), px(4)))
        for level, label in LEVELS:
            tk.Checkbutton(bar, text=label, variable=self.shown[level], command=self.rebuild, font=ui,
                           bg=PANEL, fg=COLORS[level], selectcolor=BG, activebackground=PANEL,
                           activeforeground=GOLD, highlightthickness=0, bd=0).pack(side="left", padx=(0, px(10)))
        entry = tk.Entry(bar, textvariable=self.find, font=ui, bg=BG, fg=PARCHMENT, insertbackground=GOLD,
                         relief="flat", highlightthickness=1, highlightbackground="#5a4220", highlightcolor=GOLD, width=22)
        entry.pack(side="right")
        tk.Label(bar, text="найти:", font=ui, bg=PANEL, fg=DIM).pack(side="right", padx=(px(10), px(4)))
        self.find.trace_add("write", lambda *a: self.rebuild())

        body = tk.Frame(self.win, bg=PANEL)
        body.pack(fill="both", expand=True, padx=px(10))
        self.text = tk.Text(body, bg=BG, fg=PARCHMENT, font=("Consolas", -px(12)), wrap="word", relief="flat",
                            highlightthickness=1, highlightbackground="#5a4220", padx=px(8), pady=px(6),
                            selectbackground="#6b4c1c", insertwidth=0, cursor="arrow")
        scroll = tk.Scrollbar(body, command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        for level, color in COLORS.items():
            self.text.tag_configure(level, foreground=color)
        self.text.tag_configure("time", foreground="#6f6250")
        self.text.tag_configure("found", background="#4a3a10")
        # read-only, but selectable and copyable: keys other than copying, selecting and moving do nothing
        self.text.bind("<Key>", self._key)
        menu = tk.Menu(self.win, tearoff=False)
        menu.add_command(label="Копировать", command=lambda: self.text.event_generate("<<Copy>>"))
        menu.add_command(label="Выделить всё", command=lambda: self.text.tag_add("sel", "1.0", "end"))
        self.text.bind("<Button-3>", lambda e: menu.tk_popup(e.x_root, e.y_root))

        foot = tk.Frame(self.win, bg=PANEL)
        foot.pack(fill="x", padx=px(10), pady=px(8))
        for label, action in (("Копировать показанное", self.copy_shown), ("Копировать для отчёта", self.copy_report),
                              ("Открыть файл за сегодня", self.open_file), ("Папка журналов", self.open_folder)):
            self._button(foot, label, action, ui, px).pack(side="left", padx=(0, px(8)))
        self._button(foot, "В конец ↓", lambda: self.text.see("end"), ui, px).pack(side="right")
        self.status = tk.Label(foot, text="", font=ui, bg=PANEL, fg=DIM)
        self.status.pack(side="right", padx=px(10))
        self.rebuild()

    # --- pieces ---------------------------------------------------------------------------------

    @staticmethod
    def _button(parent, label, action, font, px):
        return tk.Button(parent, text=label, command=action, font=font, bg="#23170d", fg=PARCHMENT,
                         activebackground="#3a2814", activeforeground=GOLD, relief="flat", bd=0,
                         highlightthickness=1, highlightbackground="#8a6420", padx=px(10), pady=px(3), cursor="hand2")

    def _key(self, event):
        ctrl = event.state & 0x4
        if ctrl and event.keysym.lower() in ("c", "a", "insert") or event.keysym in (
                "Up", "Down", "Left", "Right", "Prior", "Next", "Home", "End"):
            if ctrl and event.keysym.lower() == "a":
                self.text.tag_add("sel", "1.0", "end")
                return "break"
            return None
        return "break"

    def wanted(self, level: str, message: str) -> bool:
        needle = self.find.get().strip().lower()
        return self.shown[level].get() and (not needle or needle in message.lower())

    def _insert(self, item) -> None:
        time, level, message = item
        self.text.insert("end", f"{time} ", "time", f"{level:<5} ", level, message + "\n", level)

    # --- the lines --------------------------------------------------------------------------------

    def at_bottom(self) -> bool:
        return self.text.yview()[1] >= 0.999

    def append(self, items) -> None:
        """New lines: added to the view; it follows them only if it was at the bottom already."""
        follow = self.at_bottom()
        added = False
        for item in items:
            if self.wanted(item[1], item[2]):
                self._insert(item)
                added = True
        if not added:
            return
        excess = int(self.text.index("end-1c").split(".")[0]) - KEEP
        if excess > 0:
            self.text.delete("1.0", f"{excess + 1}.0")
        if follow:
            self.text.see("end")
        self._count()

    def rebuild(self) -> None:
        self.text.delete("1.0", "end")
        for item in list(self.lines)[-KEEP:]:
            if self.wanted(item[1], item[2]):
                self._insert(item)
        needle = self.find.get().strip()
        if needle:                                       # the text searched for, marked in the lines shown
            start = "1.0"
            while True:
                pos = self.text.search(needle, start, "end", nocase=True)
                if not pos:
                    break
                end = f"{pos}+{len(needle)}c"
                self.text.tag_add("found", pos, end)
                start = end
        self.text.see("end")
        self._count()

    def _count(self) -> None:
        shown = int(self.text.index("end-1c").split(".")[0]) - 1
        self.status.config(text=f"строк: {max(0, shown)}")

    # --- actions ----------------------------------------------------------------------------------

    def _clip(self, text: str, what: str) -> None:
        self.win.clipboard_clear()
        self.win.clipboard_append(text)
        self.status.config(text=f"скопировано: {what}")

    def copy_shown(self) -> None:
        self._clip(self.text.get("1.0", "end-1c"), "показанные строки")

    def copy_report(self) -> None:
        """For a bug report: versions, the card and the settings changed (`header`), then the last 300
        lines of every level whatever the filters show - the home folder and the WoW account hidden."""
        from .model import hide_private
        try:
            head = self.header() if self.header else ""
        except Exception as e:  # noqa: BLE001 - the lines are worth copying without it
            head = f"(сведения не собрались: {e})"
        tail = hide_private("\n".join(f"{t} {lv:<5} {m}" for t, lv, m in list(self.lines)[-300:]))
        self._clip(f"{head}\n\n{tail}" if head else tail, "сведения и последние 300 строк")

    def open_file(self) -> None:
        today = self.log_dir / f"bv-{datetime.now():%Y-%m-%d}.log"
        self._open(today if today.exists() else self.log_dir)

    def open_folder(self) -> None:
        self._open(self.log_dir)

    def _open(self, path: Path) -> None:
        try:
            os.startfile(path)                                            # noqa: S606
        except (OSError, AttributeError) as e:
            self.status.config(text=f"не открылось: {e}")

    def lift(self) -> None:
        self.win.deiconify()
        self.win.lift()

    def close(self) -> None:
        self.win.destroy()
        self.on_close()
