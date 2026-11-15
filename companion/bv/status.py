"""The companion's word back to the addon: CompanionStatus.lua in the addon's folder.

The game reads an addon's Lua files from disk at every load - login and /reload - so a Lua file
the companion rewrites is a channel back, if only at those moments (the way VoiceList.lua is). The
companion writes the time into it every EVERY seconds from its start, before it launches the game
and while its models load; the addon compares that time with its own clock when it loads and says
in the chat whether the reading works. The file ships with the addon (BarrensVoiceStatus = nil), so
it exists when the game starts: the client sees only files that were there at its launch.

Sound files as flags (PlaySoundFile tells an empty file from a valid one, as wow-ai uses) would be
a channel during play too, but the WoW Forever client tried reports every file that was there at
launch as playable, whatever is in it - so it tells nothing.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

EVERY = 15.0                      # seconds between writes (the addon's Companion.lua: FRESH = 3 of them)
FILE = "CompanionStatus.lua"


def write(addon: Path, now: float | None = None) -> bool:
    """The status file with the time now (epoch seconds, as the game's time()); False if it failed."""
    now = int(time.time() if now is None else now)
    path = Path(addon) / FILE
    text = ("-- Written by the Barrens Voice companion app every 15 seconds while it runs; the addon reads it\n"
            "-- at login and /reload (Companion.lua).\n"
            f"BarrensVoiceStatus = {{ beat = {now} }}\n")
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
        return True
    except OSError:               # the game reading it this very moment: next time
        return False


class Beat(threading.Thread):
    """Writes the status file every EVERY seconds, from the companion's start to its end."""

    def __init__(self, addon: Path | None, log):
        super().__init__(daemon=True, name="status")
        self.addon, self.log = addon, log
        self.stopped = threading.Event()

    def run(self) -> None:
        if self.addon is None:
            self.log("папка аддона не найдена: аддон не узнает, что компаньон работает")
            return
        while True:
            write(self.addon)
            if self.stopped.wait(EVERY):
                return

    def stop(self) -> None:
        self.stopped.set()


class SeenLines:
    """The ids of chat lines already read (a line the addon sends again is read once), kept on disk
    so a restarted companion knows them too."""

    def __init__(self, path: Path, keep: int = 500):
        self.path, self.keep = Path(path), keep
        try:
            self.ids = self.path.read_text(encoding="utf-8").split()[-keep:]
        except OSError:
            self.ids = []
        self.known = set(self.ids)

    def seen(self, line_id: str) -> bool:
        """True if this line was read already; else it is noted as read now."""
        if not line_id:
            return False
        if line_id in self.known:
            return True
        self.ids.append(line_id)
        self.known.add(line_id)
        if len(self.ids) > self.keep * 2:
            self.ids = self.ids[-self.keep:]
            self.known = set(self.ids)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text("\n".join(self.ids[-self.keep:]), encoding="utf-8")
        except OSError:
            pass
        return False
