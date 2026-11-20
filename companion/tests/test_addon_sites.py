"""CurseForge and Wago Addons: what the packager zips (.pkgmeta) and what tools/addon_sites.py makes of a release."""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import addon_sites  # noqa: E402


def pkgmeta_list(key: str) -> list[str]:
    """A top-level list of .pkgmeta (`ignore:` and its `  - item` lines)."""
    out, inside = [], False
    for line in (ROOT / ".pkgmeta").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith((" ", "#")):
            inside = line.rstrip() == f"{key}:"
        elif inside and line.strip().startswith("- "):
            out.append(line.strip()[2:])
    return out


class AddonSites(unittest.TestCase):
    def test_pkgmeta_leaves_only_the_addon(self):
        # every top-level entry git tracks is ignored, but the addon (moved to the zip's top), LICENSE (goes with
        # the code) and dot files (the packager leaves them out): a new folder of the program must not reach the sites
        tracked = subprocess.run(["git", "ls-tree", "--name-only", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                                 check=True).stdout.split()
        ignored = set(pkgmeta_list("ignore"))
        kept = {name for name in tracked if not name.startswith(".") and name not in ignored}
        self.assertEqual(kept, {"addon", "LICENSE"})
        self.assertIn("addon/BarrensVoice/Media/README.md", ignored)
        self.assertEqual({f"addon/BarrensVoice/{n}" for n in addon_sites.LEFT_OUT} - ignored, set(),
                         "what the zip check leaves out is ignored")
        text = (ROOT / ".pkgmeta").read_text(encoding="utf-8")
        self.assertIn("package-as: BarrensVoice", text)
        self.assertIn("  BarrensVoice/addon/BarrensVoice: BarrensVoice", text)
        self.assertIn(f"filename: {addon_sites.NOTES.name}", text)

    def test_the_zip_is_the_addon_and_nothing_else(self):
        tracked = ["BarrensVoice.toc", "Core.lua", "Media/chat.tga", "Media/README.md"]
        good = ["BarrensVoice/", "BarrensVoice/BarrensVoice.toc", "BarrensVoice/Core.lua", "BarrensVoice/Media/",
                "BarrensVoice/Media/chat.tga", "BarrensVoice/LICENSE"]
        self.assertEqual(addon_sites.zip_problems(good, tracked), [])
        self.assertEqual(addon_sites.zip_problems(good + ["BarrensVoice/companion/bv/app.py"], tracked),
                         ["not the addon's: BarrensVoice/companion/bv/app.py"])
        self.assertEqual(addon_sites.zip_problems(good + ["BarrensVoice/Media/README.md"], tracked),
                         ["not the addon's: BarrensVoice/Media/README.md"])
        self.assertEqual(addon_sites.zip_problems([n for n in good if not n.endswith("Core.lua")], tracked),
                         ["missing: BarrensVoice/Core.lua"])
        nested = [n.replace("BarrensVoice/", "BarrensVoice/addon/BarrensVoice/", 1) for n in good]
        self.assertTrue(addon_sites.zip_problems(nested, tracked), "move-folders not done: wrong")

    def test_only_a_release_goes_to_the_sites(self):
        entries = [{"version": "0.4.0"}, {"version": "0.3.0"}]
        self.assertEqual(addon_sites.problems("v0.4.0", "0.4.0", entries), [])
        self.assertIn("test build", addon_sites.problems("v0.4.0-beta.23", "0.4.0", entries)[0])
        self.assertIn("not a tag of version", addon_sites.problems("v0.3.0", "0.4.0", entries)[0])
        self.assertIn("no entry", addon_sites.problems("v0.5.0", "0.5.0", entries)[0])

    def test_the_sites_changelog(self):
        entries = [{"version": "0.4.0", "title": "Установщик и обновления", "items": ["Один.", "Два."]}]
        text = addon_sites.notes("0.4.0", entries, "v0.4.0")
        self.assertTrue(text.startswith("### Установщик и обновления\n\n- Один.\n- Два.\n\n"), text)
        self.assertIn("Barrens Voice Launcher", text)
        self.assertIn("https://github.com/rgeraskin/barrens-voice/releases/tag/v0.4.0", text)
        self.assertIn("/blob/v0.4.0/CHANGELOG.md", text)
        self.assertNotIn(";", text)                           # a player's text: no semicolons
        real = addon_sites.release.news_entries()             # the version in work's entry reads
        addon_sites.notes(real[0]["version"], real, "v" + real[0]["version"])


if __name__ == "__main__":
    unittest.main()
