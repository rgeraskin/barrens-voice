"""The icon by the clock: the launcher waits there when started with --tray (at Windows sign-in) and while a
game it started runs (the window's cross quits otherwise).
pystray runs its own Windows message loop on a thread; its clicks reach the window through a
queue the window empties (tkinter must be touched from its own thread only)."""
from __future__ import annotations

import queue

from .paint import ICON_FILE


class Tray:
    def __init__(self, events: queue.Queue, title: str = "Barrens Voice"):
        self.events, self.title = events, title
        self.icon = None

    def start(self) -> bool:
        try:
            import pystray
            from PIL import Image
        except ImportError:
            return False
        send = self.events.put
        menu = pystray.Menu(
            pystray.MenuItem("Открыть", lambda: send("show"), default=True),   # also a click on the icon
            pystray.MenuItem("Играть", lambda: send("play")),
            pystray.MenuItem("Выход", lambda: send("quit")))
        self.icon = pystray.Icon("BarrensVoice", Image.open(ICON_FILE), self.title, menu)
        self.icon.run_detached()
        return True

    def notify(self, text: str) -> None:
        if self.icon is not None:
            try:
                self.icon.notify(text, self.title)
            except Exception:  # noqa: BLE001 - a missed balloon is no harm
                pass

    def tooltip(self, text: str) -> None:
        if self.icon is not None:
            self.icon.title = text[:120]

    def stop(self) -> None:
        if self.icon is not None:
            self.icon.stop()
            self.icon = None
