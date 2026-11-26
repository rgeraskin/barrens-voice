"""tools/f5_stutter.py's report: what the stand-in's frames did while a run's lines were made."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import f5_stutter  # noqa: E402

RUN = {"steps": 6, "load": [1.0, 4.0], "lines": [{"start": 10.0, "end": 11.0, "calls": 2},
                                                  {"start": 20.0, "end": 20.5, "calls": 1}]}


class Summary(unittest.TestCase):
    def test_only_the_frames_while_lines_are_made_count(self):
        rows = [(2.0, 50.0),                                   # loading the voices: its own figure
                (5.0, 200.0),                                  # before the lines: not counted
                (10.0, 40.0), (10.3, 70.0), (10.6, 100.0),     # the first line, its start inside: three hitches
                (10.8, 6.0), (11.0, 101.0),                    # ... a quick frame; one at its very end, long
                (15.0, 90.0),                                  # between the lines: not counted
                (20.2, 33.0), (20.4, 6.0), (25.0, 6.0)]        # the second: 33 ms is no hitch
        s = f5_stutter.summary(rows, RUN)
        self.assertEqual((s["seconds"], s["frames"], s["calls"]), (1.5, 7, 3))
        self.assertEqual((s["hitches"], s["per_call"], s["long"]), (4, 1.3, 1))      # 100 ms is not «over 100»
        self.assertEqual((s["median_hitch_ms"], s["longest_ms"], s["stood_s"]), (85, 101, 0.3))
        self.assertEqual(s["loading_longest_ms"], 50)

    def test_the_longest_frame_is_any_frame(self):
        rows = [(0.0, 6.0), (10.5, 20.0), (20.6, 6.0)]
        s = f5_stutter.summary(rows, RUN)
        self.assertEqual((s["hitches"], s["median_hitch_ms"], s["longest_ms"], s["stood_s"]), (0, 0, 20, 0.0))

    def test_a_run_without_frames_is_an_error(self):
        # an empty CSV, or frames from another time (a probe that ended at once on a stop file left over, one started
        # late or ended early), must not read as a card that never stutters
        for rows in ([], [(1.0, 6.0), (5.0, 6.0)], [(15.0, 6.0), (30.0, 6.0)], [(9.0, 6.0), (20.2, 6.0)],
                     [(10.5, 6.0), (21.0, 6.0)]):
            with self.assertRaises(ValueError, msg=rows):
                f5_stutter.summary(rows, RUN)
        f5_stutter.summary([(10.0, 6.0), (20.5, 6.0)], RUN)          # from the first start to the last end: enough

    def test_calls_on_some_lines_only(self):
        run = {**RUN, "lines": [RUN["lines"][0], {"start": 20.0, "end": 20.5}]}
        self.assertIsNone(f5_stutter.summary([(10.0, 6.0), (20.5, 6.0)], run)["calls"])

    def test_calls_not_recorded(self):
        # a bench from before the count (26.11): no per-call figure, not one call a line
        run = {"steps": 10, "load": [1.0, 2.0], "lines": [{"start": 10.0, "end": 11.0}]}
        s = f5_stutter.summary([(5.0, 6.0), (10.5, 70.0), (12.0, 6.0)], run)
        self.assertEqual((s["calls"], s["per_call"], s["hitches"], s["loading_longest_ms"]), (None, None, 1, None))

    def test_loading_counts_only_its_own_frames(self):
        s = f5_stutter.summary([(0.5, 90.0), (2.0, 50.0), (4.5, 80.0), (10.5, 6.0), (21.0, 6.0)], RUN)
        self.assertEqual(s["loading_longest_ms"], 50)


class Report(unittest.TestCase):
    def test_the_card_without_f5_is_the_pauses_between_lines(self):
        rows = [(5.0, 90.0), (11.1, 50.0), (15.0, 7.0), (19.95, 60.0), (25.0, 6.0)]
        self.assertEqual(f5_stutter.between_lines(rows, RUN), [7.0])

    def test_from_the_files(self):
        with tempfile.TemporaryDirectory() as d:
            frames, run = Path(d, "frames.csv"), Path(d, "steps-6.json")
            frames.write_text("0.5,6.0\n10.5,70.0\n21.0,6.0\n", encoding="utf-8")
            run.write_text(json.dumps(RUN), encoding="utf-8")
            out = StringIO()
            with redirect_stdout(out):
                f5_stutter.report(str(frames), [str(run)])
            self.assertIn("6 steps: lines made in 1.5 s by 3 F5 calls, 1 frames; over 33 ms 1 (0.3 a call; ",
                          out.getvalue())
            self.assertNotIn("between lines", out.getvalue())          # no frame in the pause: no baseline line
            frames.write_text("0.5,6.0\n10.5,70.0\n15.0,8.0\n21.0,6.0\n", encoding="utf-8")
            out = StringIO()
            with redirect_stdout(out):
                f5_stutter.report(str(frames), [str(run)])
            self.assertIn("between lines (no synthesis): 1 frames, median 8.0 ms, longest 8 ms", out.getvalue())
            run.write_text(json.dumps({**RUN, "lines": [{k: v for k, v in line.items() if k != "calls"}
                                                         for line in RUN["lines"]]}), encoding="utf-8")
            out = StringIO()
            with redirect_stdout(out):
                f5_stutter.report(str(frames), [str(run)])
            self.assertIn("F5 calls not recorded", out.getvalue())
            self.assertNotIn("a call", out.getvalue())
            self.assertIn("loading the voices: no frame recorded", out.getvalue())
            frames.write_text("", encoding="utf-8")
            with self.assertRaises(SystemExit):
                f5_stutter.report(str(frames), [str(run)])


if __name__ == "__main__":
    unittest.main()
