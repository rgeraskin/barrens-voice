"""tools/stats.py: the users counted from the releases' downloads."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import stats  # noqa: E402


def release(tag, prerelease, setup, archive, manifest, draft=False):
    return {"tag_name": tag, "published_at": "2026-11-21T10:00:00Z", "prerelease": prerelease, "draft": draft,
            "assets": [{"name": "BarrensVoice-Setup.exe", "download_count": setup},
                       {"name": f"barrens-voice-{tag[1:]}.zip", "download_count": archive},
                       {"name": "manifest.json", "download_count": manifest},
                       {"name": "manifest.json.sig", "download_count": manifest}]}


class Stats(unittest.TestCase):
    def test_a_release_row(self):
        self.assertEqual(stats.row(release("v0.4.0", False, 7, 5, 40)),
                         {"tag": "v0.4.0", "date": "2026-11-21", "test": False, "setup": 7, "updated": 5,
                          "checks": 40})

    def test_the_totals_and_the_stable_ones(self):
        text = stats.report([release("v0.4.1-beta.1", True, 1, 2, 3), release("v0.4.0", False, 10, 20, 30),
                             release("v0.4.2", False, 99, 99, 99, draft=True)])
        lines = text.splitlines()
        self.assertEqual(len(lines), 5)                             # header, two releases, the totals; no draft
        self.assertEqual(lines[-2].split()[-3:], ["11", "22", "33"])
        self.assertEqual(lines[-1].split()[-3:], ["10", "20", "30"])


if __name__ == "__main__":
    unittest.main()
