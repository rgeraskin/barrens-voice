"""The strip's side of the main loop (bv/bridge.py) with a fake capture and clock: the window, the
link with the addon, a covered strip, another protocol, the whole-window search, new frames."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bv import protocol  # noqa: E402
from bv.bridge import StripReader, decode  # noqa: E402

POLL = 0.05
WINDOW = (1, (0, 0, 1920, 1080))     # (hwnd, client area), as window.find_wow_window gives it
START = 1000.0


class FakeCapturer:
    """capture.Capturer as StripReader uses it: `window` found, `grabs` handed out in turn (an
    exception raised, None when there are none left), `whole` for grab_full."""

    def __init__(self):
        self.window, self.grabs, self.whole = WINDOW, [], None
        self.rect = (0, 0, 1920, 16)
        self.finds = self.fulls = 0
        self.used, self.kept = [], []

    def find(self):
        self.finds += 1
        return self.window

    def grab(self):
        grabbed = self.grabs.pop(0) if self.grabs else None
        if isinstance(grabbed, Exception):
            raise grabbed
        return grabbed

    def grab_full(self):
        self.fulls += 1
        return self.whole

    def use(self, rect):
        self.used.append(rect)
        self.rect = rect

    def remember(self, place):
        self.kept.append(place)


def frame(seq, cell=2):
    return protocol.Frame(seq=seq, payload=b"", cell=cell)


class Base(unittest.TestCase):
    hit = None                       # what the whole-window search finds

    def setUp(self):
        self.logged, self.reports, self.found = [], [], []
        self.capturer = FakeCapturer()
        self.now = START
        # the fake capture hands out what the decoder would say: (frame, failure, other protocol)
        self.strip = StripReader(self.capturer, {"poll_interval": POLL, "capture_height": 16}, self.logged.append,
                                 lambda **f: self.reports.append(f), decode=lambda grabbed: grabbed,
                                 find=self.find, clock=lambda: self.now)

    def find(self, *args, **kwargs):
        self.found.append((args, kwargs))
        return self.hit

    def at(self, t, got=None, failure="absent", other=0):
        """A decoded grab `t` seconds after START (observe: the bookkeeping alone)."""
        self.now = START + t
        return self.strip.observe(got, failure, self.now, other)

    def take(self):
        """(lines logged, state reports) since the last take."""
        logged, reports = list(self.logged), list(self.reports)
        self.logged.clear()
        self.reports.clear()
        return logged, reports


class Bookkeeping(Base):
    def test_first_frame_then_new_ones(self):
        step = self.at(0, frame(7))
        self.assertEqual((step.frame.seq, step.first, step.pause), (7, True, POLL))   # up before the start: not news
        self.assertEqual(self.take(), (["связь с аддоном есть", "    ячейка полоски: 2 px"], [{"linked": True}]))
        self.assertIsNone(self.at(0.1, frame(7)).frame)            # the same frame: nothing new
        step = self.at(0.2, frame(8))
        self.assertEqual((step.frame.seq, step.first), (8, False))
        self.assertEqual(self.take(), ([], []))                    # linked already
        self.assertIsNone(self.at(0.3).frame)
        self.assertEqual(self.at(0.4, frame(7)).frame.seq, 7)      # another number, even an older one, is new

    def test_lost_after_five_seconds_of_misses(self):
        self.at(0, frame(1))
        self.take()
        for _ in range(int(5 / POLL) - 1):
            self.at(0)
        self.assertEqual(self.take(), ([], []))
        self.at(0)
        self.assertEqual(self.take(), (["полоска аддона пропала: озвучка выключена в игре (/bv off), экран загрузки или полоску закрыл другой аддон?"],
                                       [{"linked": False}]))
        for _ in range(200):
            self.at(0)
        self.assertEqual(self.take(), ([], []))                    # told once
        self.at(0, frame(1))
        self.assertEqual(self.take()[1], [{"linked": True}])
        self.assertIsNone(self.at(0, frame(1)).frame)              # its number is still the one read

    def test_misses_count_again_after_a_frame(self):
        self.at(0, frame(1))
        for _ in range(int(5 / POLL) - 1):
            self.at(0, failure="damaged")
        self.at(0, frame(1))
        for _ in range(int(5 / POLL) - 1):
            self.at(0)
        self.assertTrue(self.strip.linked)

    def test_covered(self):
        self.at(0, frame(1))
        self.take()
        self.at(0.1, failure="damaged")
        self.at(1.05, failure="damaged")
        self.assertEqual(self.take(), ([], []))                    # under a second of damaged frames: a chance
        self.at(1.15, failure="damaged")
        self.assertEqual(self.take(), (["полоска видна, но не читается: её что-то перекрывает?",
                                        "    миникарта, окно другого аддона или настройки изображения, искажающие цвета"],
                                       [{"damaged": True}]))
        self.at(3, failure="damaged")
        self.assertEqual(self.take(), ([], []))                    # told once
        self.at(3.1, frame(2))
        self.assertEqual(self.take(), (["полоска снова читается"], [{"damaged": False}]))
        self.at(3.2, failure="damaged")
        self.at(4.3, failure="damaged")                            # covered again: told again
        self.assertEqual(self.take()[1], [{"damaged": True}])
        self.at(4.4)                                               # gone, not covered: no words for it
        self.assertEqual(self.take(), ([], [{"damaged": False}]))
        self.at(4.5, failure="damaged")
        self.at(5.0, frame(3))
        self.at(5.1, failure="damaged")
        self.at(5.7, failure="damaged")                            # the time counts from the last cover
        self.assertEqual(self.take(), ([], []))

    def test_another_protocol_after_three_seconds(self):
        newer = protocol.VERSION + 1
        self.at(0, failure="version", other=newer)
        self.at(2.9, failure="version", other=newer)
        self.assertEqual(self.take(), ([], []))
        self.at(3.1, failure="version", other=newer)
        which, words = protocol.mismatch(newer)
        self.assertEqual(self.take(), ([words, f"    протокол полоски: у аддона {newer}, у лаунчера {protocol.VERSION}"],
                                       [{"mismatch": which}]))
        self.at(8, failure="version", other=newer)
        self.assertEqual(self.take(), ([], []))                    # told once
        self.at(8.1)
        self.assertEqual(self.take(), ([], [{"mismatch": ""}]))
        self.at(9, failure="version", other=newer)
        self.at(11, frame(1))                                      # interrupted: the 3 s start again
        self.take()
        self.at(12, failure="version", other=0)
        self.at(14.9, failure="version", other=0)
        self.assertEqual(self.take(), ([], []))
        self.at(15.1, failure="version", other=0)
        self.assertEqual(self.take()[1], [{"mismatch": "older"}])

    def test_whole_window_search(self):
        self.capturer.whole = (b"picture", 1920, 1080)
        self.hit = (0, 1064, 600, 64, frame(1))
        self.at(0)
        self.at(1.9)
        self.assertEqual(self.found, [])                           # absent under 2 s: not looked for yet
        self.at(2.1)
        self.assertEqual(self.found, [((b"picture", 1920, 1080), {"width_hint": 1920, "capture_height": 64})])
        self.assertEqual(self.capturer.used, [(0, 1064, 600, 64)])
        self.assertEqual(self.take()[0], ["полоска найдена в другом месте: x 0, y 1064, ширина 600"])
        self.assertEqual(self.capturer.kept, [])                   # not before a frame is read from there
        self.at(7.0)
        self.assertEqual(len(self.found), 1)                       # every 5 s, not every poll
        self.at(7.2)
        self.assertEqual(len(self.found), 2)
        self.assertEqual(self.found[1][1]["width_hint"], 600)      # the width now grabbed
        self.assertEqual(self.capturer.used, [(0, 1064, 600, 64)])   # found where it is grabbed: kept
        self.assertEqual(self.take()[0], [])
        self.hit = None
        self.at(12.3)
        self.assertEqual(len(self.found), 3)                       # nothing found: kept looking
        self.capturer.whole = None                                 # no picture of the window yet
        self.at(17.4)
        self.assertEqual((len(self.found), self.capturer.fulls), (3, 4))

    def test_the_search_place_kept_once_read(self):
        # a hit can be wrong (a strip half covered by another addon): kept for a restart only once a frame is
        # read from the rectangle it gave, in the window's pixels
        self.capturer.whole = (b"picture", 1920, 1080)
        self.hit = (0, 1064, 600, 64, frame(1))
        self.at(0)
        self.at(2.1)
        self.assertEqual(self.capturer.kept, [])
        self.at(2.2)                                               # still nothing read there
        self.assertEqual(self.capturer.kept, [])
        self.at(2.3, frame(1))
        self.assertEqual(self.capturer.kept, [(0, 1064, 600, 64, 1920, 1080)])
        self.at(2.4, frame(2))
        self.assertEqual(len(self.capturer.kept), 1)               # once

    def test_the_search_place_not_kept_when_the_window_changed(self):
        # a new window between the hit and the first frame: the rectangle is the addon's place again, not the hit
        self.capturer.whole = (b"picture", 1920, 1080)
        self.hit = (0, 1064, 600, 64, frame(1))
        self.at(0)
        self.at(2.1)
        self.capturer.rect = (0, 1078, 1920, 16)                   # _fit for another window
        self.at(2.3, frame(1))
        self.assertEqual(self.capturer.kept, [])
        self.at(2.4, frame(2))
        self.assertEqual(self.capturer.kept, [])                   # nor later

    def test_a_strip_thicker_than_asked_is_looked_for(self):
        self.strip.config["capture_height"] = 80
        self.capturer.whole = (b"picture", 1920, 1080)
        self.at(0)
        self.at(2.1)
        self.assertEqual(self.found[0][1]["capture_height"], 80)

    def test_search_waits_for_two_seconds_of_absence_again(self):
        self.capturer.whole = (b"picture", 1920, 1080)
        self.at(0)
        self.at(2.1)
        self.assertEqual(len(self.found), 1)
        self.at(7.0, frame(1))
        self.at(7.3)
        self.at(9.2)
        self.assertEqual(len(self.found), 1)                       # 2 s after the frame, not at once
        self.at(9.4)
        self.assertEqual(len(self.found), 2)
        self.at(9.5, frame(2))
        self.at(9.6, failure="damaged")
        self.at(20, failure="damaged")                             # a damaged strip is no absent one
        self.assertEqual(len(self.found), 2)


class Polling(Base):
    """poll: the window, the grab, the pause before the next poll."""

    def poll(self, *grabs):
        self.capturer.grabs = list(grabs)
        return self.strip.poll(self.now)

    def test_window(self):
        self.capturer.window = None
        self.assertEqual(self.poll().pause, 1.0)
        self.assertEqual(self.take(), (["окно игры не найдено или свёрнуто — жду"], [{"window": False}]))
        self.now += 1
        self.poll()
        self.assertEqual((self.take(), self.capturer.finds), (([], []), 2))    # looked for every poll, told once
        self.capturer.window = WINDOW
        self.now += 1
        step = self.poll((frame(3), "", 0))
        self.assertEqual((step.frame.seq, step.pause), (3, POLL))
        self.assertEqual(self.take(), (["окно WoW: (0, 0, 1920, 1080)", "связь с аддоном есть",
                                        "    ячейка полоски: 2 px"], [{"window": True}, {"linked": True}]))
        self.now += 2
        self.poll()
        self.assertEqual(self.capturer.finds, 3)                   # found: looked for again only after 2 s
        self.now += 0.1
        self.poll()
        self.assertEqual(self.capturer.finds, 4)
        self.assertEqual(self.take(), ([], []))                    # the same window: no words
        self.capturer.window = None
        self.now += 2.1
        self.assertEqual(self.poll().pause, 1.0)
        # minimized: the link goes with the window (the launcher said «связь есть» under a minimized game)
        self.assertEqual(self.take(), (["окно игры не найдено или свёрнуто — жду"], [{"window": False}, {"linked": False}]))
        self.capturer.window = WINDOW
        self.now += 1
        self.poll((frame(4), "", 0))
        self.assertEqual(self.take()[1], [{"window": True}, {"linked": True}])     # back: linked again

    def test_grab(self):
        self.poll()
        self.take()
        self.assertEqual(self.poll(None).pause, POLL)              # nothing grabbed yet: no frame, no miss
        self.assertEqual(self.strip.misses, 0)
        self.now += 0.1
        self.assertEqual(self.poll(OSError("closed")).pause, 1.0)
        self.assertEqual(self.take(), (["снимок не удался: closed"], []))
        self.assertEqual(self.capturer.finds, 1)
        self.now += 0.1
        self.poll(OSError("closed"))
        self.assertEqual(self.take(), ([], []))                    # once while it keeps failing
        self.assertEqual(self.capturer.finds, 2)                   # the window looked for again at once
        self.now += 0.1
        self.poll((frame(1), "", 0))
        self.take()
        self.now += 0.1
        self.poll(OSError("closed again"))
        self.assertEqual(self.take(), (["снимок не удался: closed again"], []))

    def test_the_time_is_taken_after_the_grab(self):
        # the bookkeeping's time is the clock's after the grab, not the loop's `now` from before it
        self.capturer.whole = (b"picture", 1920, 1080)
        for t in range(5):
            self.now = START + t
            self.capturer.grabs = [(None, "absent", 0)]
            self.strip.poll(START)
        self.assertEqual(len(self.found), 1)


class RealDecoder(unittest.TestCase):
    def test_decode_says_why(self):
        self.assertEqual(decode((bytes(1920 * 4 * 2), 1920, 2))[:2], (None, "absent"))


if __name__ == "__main__":
    unittest.main()
