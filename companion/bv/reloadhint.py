"""Whether to remind the player that the hidden chat needs a /reload.

The addon hides the chat windows («Прятать окно чата») only when, at login or its last /reload, the
companion's status file had a fresh beat (Companion.lua, ChatFade.lua) - it reads the file only then.
A companion started while the player is already in the world comes after that check, and the chat
stays visible until /reload. So the reminder is asked for just before this companion's first beat:
- «Прятать окно чата» is on in the addon's saved settings, and the addon is not switched off;
- no companion was running a moment ago (a restart by the launcher: the addon saw the previous one);
- the strip is on screen now: the player is in the world, the addon loaded before this beat.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

RECENT = 60.0      # seconds: a companion beating or stopped this recently was there at the player's login


def status_recent(addon_dir: Path | None, now: float | None = None) -> bool:
    """Was a companion running a moment ago, by the status file it leaves in the addon's folder?"""
    if addon_dir is None:
        return False
    try:
        text = (Path(addon_dir) / "CompanionStatus.lua").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    times = [int(n) for n in re.findall(r"\b(?:beat|stopped)\s*=\s*(\d+)", text)]
    now = time.time() if now is None else now
    return any(t and abs(now - t) <= RECENT for t in times)


def strip_in_view(config: dict) -> bool:
    """The addon's strip in the game window now (read or covered): the player is in the world."""
    from . import locate, protocol
    from .capture import Capturer
    capturer = Capturer(config, lambda *a: None)
    try:
        if not capturer.find():
            return False
        known = locate.known_place(config)
        if known:
            capturer.set_place(known[0])
        for _ in range(20):                         # Windows Graphics Capture: its first frame takes a moment
            grabbed = capturer.grab()
            if grabbed is not None:
                frame = protocol.decode(protocol.Image(*grabbed))
                return frame is not None or protocol.last_failure in ("damaged", "version")
            time.sleep(0.1)
        return False
    except Exception:  # noqa: BLE001 - only a hint
        return False
    finally:
        if getattr(capturer, "wgc", None):
            capturer.wgc.stop()


def needed(config: dict, addon_dir: Path | None, in_view=strip_in_view, now: float | None = None) -> bool:
    from .dictionary import saved_flag
    if not saved_flag(config, "fadeChat") or saved_flag(config, "enabled") is False:
        return False
    if status_recent(addon_dir, now):
        return False
    return in_view(config)
