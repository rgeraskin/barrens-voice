"""CurseForge and Wago Addons: what the packager zips (.pkgmeta) and what tools/addon_sites.py makes of a release."""
from __future__ import annotations

import re
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

    def test_the_toc_names_the_projects(self):
        # the sites' apps match an addon installed elsewhere (by the launcher) by these; addon-sites.yml checks them
        # against the repository's variables
        toc = (ROOT / "addon" / "BarrensVoice" / "BarrensVoice.toc").read_text(encoding="utf-8")
        self.assertRegex(toc, r"(?m)^## X-Curse-Project-ID: \d+$")
        self.assertRegex(toc, r"(?m)^## X-Wago-ID: [A-Za-z0-9]{8}$")

    def test_a_test_builds_toc_goes_without_the_ids(self):
        # the archive's TOC of a test build (release.build): the sites have releases only
        toc = b"## Interface: 16001\r\n## X-Curse-Project-ID: 1\r\n## Version: 0.4.1b1\n## X-Wago-ID: abcdEFGH\nCore.lua\n"
        self.assertEqual(addon_sites.release.without_site_ids(toc),
                         b"## Interface: 16001\r\n## Version: 0.4.1b1\nCore.lua\n")

    def test_a_release_keeps_the_ids(self):
        toc = (ROOT / "addon" / "BarrensVoice" / "BarrensVoice.toc").read_bytes()
        self.assertEqual(addon_sites.release.toc_for("0.4.1", toc), toc)
        self.assertNotIn(b"X-Wago-ID", addon_sites.release.toc_for("0.4.1b1", toc))

    def test_dry_without_the_news_entry(self):
        from unittest import mock
        with mock.patch.object(addon_sites.release, "versions", return_value={"version": "9.9.9"}), \
                mock.patch.object(addon_sites.release, "news_entries", return_value=[{"version": "0.4.0"}]), \
                mock.patch.object(addon_sites.release, "stamp_dictionary") as stamp, \
                mock.patch("sys.stderr") as err:
            self.assertEqual(addon_sites.main(None), 1)
        stamp.assert_not_called()                              # said before anything is written
        self.assertIn("no entry 9.9.9", "".join(c.args[0] for c in err.write.call_args_list))

    def test_git_of_another_repository_ignores_a_calling_gits(self):
        # a hook or `git rebase --exec` sets GIT_DIR: release._git in a test's repository must not follow it
        import os
        import tempfile
        from unittest import mock
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from gitenv import own_repository_env
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init", "-q", d], check=True, env=own_repository_env())
            with mock.patch.dict(os.environ, {"GIT_DIR": str(Path(d) / "no-such-dir")}):
                self.assertEqual(addon_sites.release._git(Path(d), "rev-parse", "--is-inside-work-tree"), "true")

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

    def test_the_addon_lists_description(self):
        # the TOC's Notes, the game's addon list (and the sites' apps): what the addon does and that it needs the
        # Windows program; how lines reach it (the strip) is for the README and the welcome, not the list
        toc = (ROOT / "addon" / "BarrensVoice" / "BarrensVoice.toc").read_text(encoding="utf-8")
        notes = re.search(r"^## Notes: (.+)$", toc, re.M).group(1)
        self.assertIn("Barrens Voice Launcher для Windows", notes)
        for detail in ("полоск", "компаньон", "F5"):
            self.assertNotIn(detail, notes)

    def test_the_sites_description(self):
        # pasted by hand into both sites (no API takes it): links and pictures work only absolute, the pictures are
        # the repository's own, the launcher is said first
        text = (ROOT / "docs" / "addon-sites-description.md").read_text(encoding="utf-8")
        links = re.findall(r"\]\(([^)\s]+)\)|src=\"([^\"]+)\"", text)
        self.assertTrue(links)
        raw = "https://raw.githubusercontent.com/rgeraskin/barrens-voice/master/"
        for link in (a or b for a, b in links):
            self.assertTrue(link.startswith("https://"), link)
            if link.startswith(raw):
                self.assertTrue((ROOT / link[len(raw):]).is_file(), link)
        self.assertLess(text.index("Barrens Voice Launcher"), text.index("## "))
        # CurseForge: English before any other language, no links that download a file (the release's page instead)
        english = text[:re.search("[а-яё]", text, re.I).start()]
        self.assertIn("Barrens Voice Launcher", english)
        self.assertIn("open-source", english)
        self.assertNotIn("/download/", text)
        self.assertNotIn(";", text)


if __name__ == "__main__":
    unittest.main()
