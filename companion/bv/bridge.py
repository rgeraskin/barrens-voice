"""The strip's side of the main loop: the WoW window looked for, its strip grabbed and decoded, and what
the companion makes of a frame or of its absence - the link with the addon found or lost, a strip
covered or of another protocol, a strip not where it was said to be (looked for over the whole window).

`StripReader.poll` is one turn of the loop; `observe` is its bookkeeping alone, for a frame (or the
reason there is none) at a given time. The capture (bv/capture.py, Windows only), the decoder and
the clock are passed in, so all of it runs in the tests on any system.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from . import locate, protocol


@dataclass(frozen=True)
class Step:
    """What one poll came to: how long to wait before the next one, and a frame with a new number."""
    pause: float
    frame: protocol.Frame | None = None
    first: bool = False             # that frame was up before the companion started: not news


def decode(grabbed) -> tuple[protocol.Frame | None, str, int]:
    """(the frame on a grab - raw BGRA bytes, width, height - or None, why there is none, the
    protocol of a strip this companion does not read)."""
    frame = protocol.decode(protocol.Image(*grabbed))
    return frame, protocol.last_failure, protocol.other_version


class StripReader:
    """The strip of the WoW window, poll by poll. `capturer` is a capture.Capturer (find, grab,
    grab_full, rect, use), `report` sets fields of tmp/state.json (state.report)."""

    WINDOW_EVERY = 2.0      # the window looked for again (moved, closed, another one)
    RETRY = 1.0             # no window, or its grab failed: the next try after this pause
    SEARCH_AFTER = 2.0      # no strip where it was said to be for this long: look over the whole window
    SEARCH_EVERY = 5.0      # ... and again at most this often (~0.3 s of work)
    DAMAGED_AFTER = 1.0     # a strip in view whose frames do not check out, told after this long
    FOREIGN_AFTER = 3.0     # a strip of another protocol held this long: not a damaged frame's chance
    LOST_AFTER = 5.0        # seconds of polls without a frame: the link with the addon is lost

    def __init__(self, capturer, config: dict, log, report, decode=decode, find=locate.find,
                 clock=time.monotonic):
        self.capturer, self.config, self.log, self.report = capturer, config, log, report
        self.decode, self.find, self.clock = decode, find, clock
        self.window, self.window_checked, self.first_check = None, 0.0, True
        self.grab_failed = False
        self.seq = None                 # the number of the last frame read
        self.linked = False
        self.misses = 0                 # polls in a row without a frame
        self.absent_since, self.searched = None, 0.0
        self.damaged_since, self.damaged_told = None, False
        self.foreign_since, self.foreign_told = None, False
        self.found = None               # a place the search found, kept once a frame is read from it

    def poll(self, now: float) -> Step:
        """One turn: the window (looked for every WINDOW_EVERY s), a grab of the strip, its frame."""
        if self.window is None or now - self.window_checked > self.WINDOW_EVERY:
            found = self.capturer.find()
            if found != self.window or self.first_check:
                self.log(f"окно WoW: {found[1]}" if found else "окно игры не найдено или свёрнуто — жду")
                self.report(window=bool(found))
            self.window, self.window_checked, self.first_check = found, now, False
        if self.window is None:
            return Step(self.RETRY)
        try:
            grabbed = self.capturer.grab()
        except Exception as e:  # noqa: BLE001 - window moved or closed between checks
            if not self.grab_failed:               # once, not every second while it keeps failing
                self.log(f"снимок не удался: {e}")
            self.grab_failed = True
            self.window_checked = 0.0              # the window looked for again, after a pause
            return Step(self.RETRY)
        self.grab_failed = False
        if grabbed is None:
            return Step(self.config["poll_interval"])
        frame, failure, other_version = self.decode(grabbed)
        return self.observe(frame, failure, self.clock(), other_version)

    def observe(self, frame: protocol.Frame | None, failure: str, now: float, other_version: int = 0) -> Step:
        """A decoded grab: `frame`, or None and why (protocol.last_failure: "absent", "damaged",
        "version" with the strip's protocol in `other_version`), at monotonic time `now`."""
        pause = self.config["poll_interval"]
        if frame is None and failure == "absent":
            self.absent_since = self.absent_since or now
            if now - self.absent_since > self.SEARCH_AFTER and now - self.searched > self.SEARCH_EVERY:
                self.searched = now
                self._search()
        elif frame is not None:
            self.absent_since = None
        if frame is None and failure == "version":
            self.foreign_since = self.foreign_since or now
            if not self.foreign_told and now - self.foreign_since > self.FOREIGN_AFTER:
                which, words = protocol.mismatch(other_version)
                self.log(words)
                self.log(f"    протокол полоски: у аддона {other_version}, у программы {protocol.VERSION}")
                self.foreign_told = True
                self.report(mismatch=which)
        elif self.foreign_since is not None:
            self.foreign_since = None
            if self.foreign_told:
                self.foreign_told = False
                self.report(mismatch="")
        if frame is None:
            self._missed(failure, now)
            return Step(pause)
        self.misses = 0
        if self.found is not None:                 # the search's place works: kept for a restart
            self.capturer.remember(self.found)
            self.found = None
        self.damaged_since = None
        if self.damaged_told:                      # readable again: a later cover is told again
            self.damaged_told = False
            self.log("полоска снова читается")
            self.report(damaged=False)
        if not self.linked:
            self.log("связь с аддоном есть")
            self.log(f"    ячейка полоски: {frame.cell} px")
            self.linked = True
            self.report(linked=True)
        if frame.seq == self.seq:
            return Step(pause)
        first = self.seq is None                   # what was up before we started: not news
        self.seq = frame.seq
        return Step(pause, frame, first)

    def _missed(self, failure: str, now: float) -> None:
        self.misses += 1
        if failure == "damaged":
            self.damaged_since = self.damaged_since or now
            if not self.damaged_told and now - self.damaged_since > self.DAMAGED_AFTER:
                self.log("полоска видна, но не читается: её что-то перекрывает?")
                self.log("    миникарта, окно другого аддона или настройки изображения, искажающие цвета")
                self.damaged_told = True
                self.report(damaged=True)
        else:
            self.damaged_since = None
            if self.damaged_told:                  # gone, not covered: its own state now (minimized, hidden UI)
                self.damaged_told = False
                self.report(damaged=False)
        if self.linked and self.misses == int(self.LOST_AFTER / self.config["poll_interval"]):
            self.log("полоска аддона пропала: игра свёрнута или скрыт интерфейс?")
            self.linked = False
            self.report(linked=False)

    def _search(self) -> None:
        """The strip anywhere in the window (locate.find); found elsewhere, it is grabbed there from now on."""
        whole = self.capturer.grab_full()
        # rows enough for a narrow strip: the addon makes it thicker so a long line fits
        hit = self.find(*whole, width_hint=self.capturer.rect[2],
                        capture_height=max(self.config["capture_height"], 64)) if whole else None
        if hit and hit[:4] != self.capturer.rect:
            self.capturer.use(hit[:4])
            self.log(f"полоска найдена в другом месте: x {hit[0]}, y {hit[1]}, ширина {hit[2]}")
            # kept for a restart once a frame is read from there (a hit can be wrong: a strip half covered by
            # another addon), in the window's pixels, the window taken for the "screen"
            self.found = (*hit[:4], whole[1], whole[2])
