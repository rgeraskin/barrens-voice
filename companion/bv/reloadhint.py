"""Whether to remind the player that the hidden chat needs a /reload.

The addon hides the chat windows («Прятать окно чата») only when, at login or its last /reload, the
companion's status file had a fresh beat (Companion.lua, ChatFade.lua) - it reads the file only then.
A companion started while the player is already in the world comes after that check, and the chat
stays visible until /reload. So the reminder is asked for just before this companion's first beat:
- «Прятать окно чата» is on in the addon's saved settings, and the addon is not switched off;
- no companion was running a moment ago (a restart by the launcher: the addon saw the previous one) -
  unless the game wrote the addon's saved variables after that companion's last word: it does so at
  /reload and logout, so the addon has loaded since, without it;
- the strip is on screen now: the player is in the world, the addon loaded before this beat.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

RECENT = 60.0      # seconds: a companion beating or stopped this recently was there at the player's login
FRESH = 45.0       # seconds the addon takes a beat for a running companion (Companion.lua C.FRESH)
# The game writes the saved variables as a /reload starts, the addon reads the status file seconds later: a /reload
# begun this long before the companion went may already have missed it. A needless reminder is harmless (it says
# «если окно чата не прячется»), a missing one leaves the chat visible without a word.
RELOAD_SLACK = 10.0


def status_recent(addon_dir: Path | None, now: float | None = None) -> float | None:
    """A companion running a moment ago, by the status file it leaves in the addon's folder: until when an
    addon loading would have taken it for running (unix time) - its stop, or its last beat and FRESH more
    (killed, it wrote no stop); None when none was."""
    if addon_dir is None:
        return None
    try:
        text = (Path(addon_dir) / "CompanionStatus.lua").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    now = time.time() if now is None else now
    stamps = {kind: int(t) for kind, t in re.findall(r"\b(beat|stopped)\s*=\s*(\d+)", text)}
    stopped, beat = stamps.get("stopped", 0), stamps.get("beat", 0)
    if stopped:                                     # it ended then: an addon loading later did not see it
        return float(stopped) if abs(now - stopped) <= RECENT else None
    return beat + FRESH if beat and abs(now - beat) <= RECENT else None


def reloaded_since(config: dict, moment: float) -> bool:
    """Did the game write the addon's saved variables after `moment` - a /reload or a logout since?"""
    from .dictionary import find_saved
    path = find_saved(config)
    try:
        return path is not None and path.stat().st_mtime > moment - RELOAD_SLACK
    except OSError:
        return False


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
    seen = status_recent(addon_dir, now)
    if seen is not None and not reloaded_since(config, seen):     # the addon loaded while it was there
        return False
    return in_view(config)
