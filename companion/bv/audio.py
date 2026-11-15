"""One player for every engine: lines play strictly one after another (winsound stops a sound when
another starts, and two engines must never talk over or cut each other), each with a short silent
tail so the sound device does not clip the last syllable. stop() cuts the line being played and
drops everything queued or still being made (the "generation" a line was asked for in)."""
from __future__ import annotations

import io
import queue
import threading
import wave

TAIL = 0.25   # seconds of silence after each line
PAUSE_MAX = 90.0   # a pause whose "resume" never came ends by itself


def wav(pcm: bytes, rate: int, volume: float = 1.0) -> bytes:
    """16-bit mono PCM as a WAV file in memory, scaled by `volume` (0..2; over 1 clipped - the
    engines go through f5engine.wav_bytes, which limits softly), with the silent tail."""
    if abs(volume - 1) > 0.001:
        import array
        samples = array.array("h", pcm)
        for i, s in enumerate(samples):
            samples[i] = max(-32768, min(32767, int(s * volume)))
        pcm = samples.tobytes()
    pcm += b"\0\0" * int(rate * TAIL)
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return out.getvalue()


def seconds(data: bytes) -> float:
    with wave.open(io.BytesIO(data)) as w:
        return w.getnframes() / w.getframerate()


def _replayed(line) -> bool:
    return getattr(line, "options", {}).get("replay") == "1"


def queue_line(lines: queue.Queue, line, limit: int, log) -> None:
    """A chat line into an engine's queue. With `limit` live lines waiting, the oldest of them is
    dropped - the reading keeps up with the chat - but never a line sent again by /bv last (asked
    for; the addon marks it replay=1): a replay waits whole and does not count toward the limit, so
    the chat that comes meanwhile keeps its own `limit` lines behind it."""
    if lines.qsize() >= limit:
        waiting = []
        while True:
            try:
                waiting.append(lines.get_nowait())
            except queue.Empty:
                break
        live = [i for i, x in enumerate(waiting) if x is not None and not _replayed(x)]
        dropped = set()
        while len(live) >= limit and not _replayed(line):
            i = live.pop(0)
            dropped.add(i)
            old = waiting[i]
            log(f"очередь полна ({limit}): не прочитано: {old.sender}: {old.text[:80]}")
        for i, x in enumerate(waiting):
            if i not in dropped:
                lines.put(x)
    lines.put(line)


class Player(threading.Thread):
    """winsound cannot play from memory asynchronously (RuntimeError), and only an asynchronous
    sound can be cut: each line is written to a file first, a few names in turn."""

    def __init__(self, max_queue: int = 8, folder=None, log=None):
        super().__init__(daemon=True, name="player")
        import tempfile
        from pathlib import Path
        self.folder = Path(folder) if folder else Path(tempfile.gettempdir()) / "barrens-voice"
        self.folder.mkdir(parents=True, exist_ok=True)
        self.turn = 0
        self.items: queue.Queue = queue.Queue()
        self.max_queue = max_queue
        self.generation = 0
        self.stopped = threading.Event()
        self.playing_until = 0.0     # monotonic time the line being played ends (or ended)
        self.log = log or (lambda *a: None)
        self.running = threading.Event()   # cleared while paused (CatQuest speaks)
        self.running.set()
        self.paused_at = 0.0
        self.current = None          # (generation, data) being played
        self.cut_by_pause = False
        self.again = None            # the line a pause cut: played again from its start

    def quiet_for(self) -> float:
        """Seconds since the last line ended; 0 while one plays or waits to."""
        import time
        if not self.items.empty() or not self.running.is_set() or self.again is not None:
            return 0.0
        return max(0.0, time.monotonic() - self.playing_until)

    def play(self, data: bytes, generation: int | None = None) -> None:
        """Queue a line; one made for an earlier generation (before a stop) is dropped. With
        max_queue lines made and waiting, it waits for room - synthesis ahead of the playing - rather
        than lose a line already made (which lines to drop is decided before they are made:
        queue_line)."""
        import time
        if generation is not None and generation != self.generation:
            return
        made_for = self.generation
        while self.items.qsize() >= self.max_queue and self.generation == made_for:
            time.sleep(0.05)
        if self.generation != made_for:          # a stop while it waited
            return
        self.items.put((self.generation, data))

    def pause(self) -> bool:
        """Hold the lines (CatQuest speaks): the one being played is cut, to be played again from its
        start on resume(). False if already paused."""
        import time
        if not self.running.is_set():
            return False
        self.paused_at = time.monotonic()
        self.running.clear()
        if self.current is not None:
            self.cut_by_pause = True
            self.stopped.set()
        return True

    def resume(self) -> bool:
        """Go on: the cut line first, then the queue. False if not paused."""
        if self.running.is_set():
            return False
        self.running.set()
        return True

    def _wait_running(self) -> None:
        import time
        while not self.running.wait(0.5):
            if time.monotonic() - self.paused_at > PAUSE_MAX:
                self.log(f"пауза для CatQuest дольше {PAUSE_MAX:.0f} с — продолжаю")
                self.running.set()

    def stop(self) -> None:
        """Cut the line being played and forget the queue."""
        self.generation += 1
        self.again = None
        while not self.items.empty():
            try:
                self.items.get_nowait()
            except queue.Empty:
                break
        self.stopped.set()

    def run(self) -> None:
        import winsound

        while True:
            item, self.again = self.again, None
            if item is None:
                item = self.items.get()
            self._wait_running()
            generation, data = item
            if generation != self.generation:
                continue
            self.stopped.clear()
            self.cut_by_pause = False
            self.current = item
            if not self.running.is_set():         # paused just now: before it started
                self.current, self.again = None, item
                continue
            self.turn = (self.turn + 1) % 3
            path = self.folder / f"line{self.turn}.wav"
            path.write_bytes(data)
            # asynchronous, so a stop can cut it
            import time
            length = seconds(data)
            self.playing_until = time.monotonic() + length
            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            if self.stopped.wait(length):
                winsound.PlaySound(None, 0)
                self.playing_until = time.monotonic()
                if self.cut_by_pause and generation == self.generation:
                    self.again = item
            self.current = None
