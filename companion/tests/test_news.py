"""«Что нового»: news.toml, the one source of the players' news (bv/news.py)."""
from __future__ import annotations

import re
import subprocess
import sys
import tomllib
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bv import news  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def entry(version="0.4.1", kind="small", **more) -> dict:
    return {"version": version, "date": "20.11.2026", "kind": kind, "title": "Проверка " + version,
            "summary": "числа читаются точнее", "items": ["Пункт."], **more}


def release_tags() -> list[str]:
    out = subprocess.run(["git", "tag", "-l", "v*"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                         errors="replace").stdout.split()
    return [t for t in out if re.fullmatch(r"v\d+\.\d+\.\d+(-beta\.\d+)?", t)]


class Source(unittest.TestCase):
    """news.toml at the repository's root: an entry per release, keyed by the program's version."""

    def test_the_file_is_well_formed(self):
        entries = news.load(ROOT / news.SOURCE)
        self.assertEqual(news.problems(entries), [])
        self.assertGreaterEqual(len(entries), 5)
        newest = entries[0]
        self.assertEqual((newest["version"], newest["kind"]), ("0.4.0", "big"))
        self.assertGreaterEqual(len(newest["items"]), 6)

    def test_every_release_has_its_news(self):
        # a release's entry is dated; a test build's is its release's (dated or not yet); the version in work has one
        entries = {e["version"]: e for e in news.load(ROOT / news.SOURCE)}
        working = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
        self.assertIn(working, entries, f"add a «Что нового» entry for {working} to news.toml")
        tags = release_tags()
        if not tags:
            self.skipTest("no release tags here (a shallow clone)")
        for tag in tags:
            version = tag[1:].split("-")[0]
            self.assertIn(version, entries, f"{tag}: news.toml needs an entry for {version}")
            if "-beta." not in tag:
                self.assertIn("date", entries[version], f"{tag}: its «Что нового» entry needs the release's date")

    def test_problems_are_found(self):
        cases = {
            "unknown fields": entry(sumary="x"),
            "version must be": entry(version="0.4"),
            "date must be a real day": entry(date="31.02.2026"),
            "kind must be": entry(kind="huge"),
            "title must be a text": entry(title=""),
            "items must be 1 to": entry(items=[]),
            "one short line": entry(summary="очень " * 30),
            "no full stop": entry(summary="числа читаются точнее."),
            "one line each": entry(summary="две\nстроки"),
            "no '→'": entry(items=["Голос → другой."]),
            "no '–'": entry(title="Голоса – свои"),
            "no '|'": entry(items=["|cffff0000красный|r"]),
            "«ты», not «вы»": entry(items=["Теперь вы слышите место."]),
        }
        for said, bad in cases.items():
            found = news.problems([bad])
            self.assertTrue(any(said in p for p in found), f"{said}: {found}")
        self.assertTrue(any("date must be" in p for p in news.problems([entry(date="2026-11-20")])))
        del_items = entry()
        del del_items["items"]
        self.assertTrue(any("items must be" in p for p in news.problems([del_items])))
        self.assertEqual(news.problems([entry("0.4.1"), entry("0.4.0")]), [])
        self.assertTrue(any("one entry a version" in p for p in news.problems([entry("0.4.1"), entry("0.4.1")])))
        self.assertTrue(any("newest first" in p for p in news.problems([entry("0.4.0"), entry("0.4.1")])))
        # the release in work (and its test builds) may lack a date, a released one may not
        undated = {k: v for k, v in entry("0.4.1").items() if k != "date"}
        beta = {k: v for k, v in entry("0.4.1b3").items() if k != "date"}
        self.assertEqual(news.problems([undated, beta, entry("0.4.0")]), [])
        old = {k: v for k, v in entry("0.4.0").items() if k != "date"}
        self.assertTrue(any("needs its date" in p for p in news.problems([entry("0.4.1"), old])))

    def test_what_a_version_shows(self):
        # News.lua's N.Visible, the same rule: its release's entry and older ones, a test build's own from that build on
        entries = [entry("0.5.0"), entry("0.4.1"), entry("0.4.1b3"), entry("0.4.0")]
        shown = lambda v: [e["version"] for e in news.visible(entries, v)]   # noqa: E731
        self.assertEqual(shown("0.4.1b1"), ["0.4.1", "0.4.0"])
        self.assertEqual(shown("0.4.1b3"), ["0.4.1", "0.4.1b3", "0.4.0"])
        self.assertEqual(shown("0.4.1"), ["0.4.1", "0.4.1b3", "0.4.0"])
        self.assertEqual(shown("0.4.0"), ["0.4.0"])
        self.assertEqual(shown("0.6.0"), ["0.5.0", "0.4.1", "0.4.1b3", "0.4.0"])
        self.assertEqual(shown("?"), [])


class Release(unittest.TestCase):
    """tools/release.py: a release needs a dated entry of its own version; the GitHub release's description is it."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT / "tools"))
        import release
        cls.release = release

    def test_a_release_needs_its_dated_entry(self):
        problem = self.release.news_problem
        dated, undated = entry("0.4.1"), {k: v for k, v in entry("0.4.1").items() if k != "date"}
        self.assertIsNone(problem("0.4.1", [dated, entry("0.4.0")]))
        # the program's version, not the addon's: a release of the program alone needs its own entry too
        self.assertIn("no «Что нового» entry", problem("0.4.1", [entry("0.4.0")]))
        self.assertIn("has no date", problem("0.4.1", [undated, entry("0.4.0")]))
        # a test build: its release's entry may be missing or undated yet
        self.assertIsNone(problem("0.4.1b2", [entry("0.4.0")]))
        self.assertIsNone(problem("0.4.1b2", [undated, entry("0.4.0")]))
        # a news.toml with a problem stops any build: the archive carries it to the game
        self.assertIn("news.toml: ", problem("0.4.1b2", [entry("0.4.1", kind="huge")]))

    def test_the_build_refuses_it(self):
        import os
        from unittest import mock
        release = self.release
        undated = {k: v for k, v in entry("9.9.9").items() if k != "date"}
        for entries, said in (([entry("0.4.0")], "no «Что нового» entry"), ([undated], "has no date")):
            with mock.patch.object(release, "versions", return_value={"version": "9.9.9", "addon": "9.9.9", "protocol": 1}), \
                    mock.patch.object(release, "news_entries", return_value=entries), \
                    mock.patch.dict(os.environ, {"RELEASE_TAG": "v9.9.9"}), self.assertRaises(SystemExit) as stop:
                release.build()
            self.assertIn(said, str(stop.exception))

    def test_the_release_description(self):
        entries = [entry("0.4.1", items=["Числа читаются точнее.", "Новые слова в словаре."]), entry("0.4.0")]
        link = "Полный список изменений, на английском: [CHANGELOG.md](https://github.com/rgeraskin/barrens-voice/blob/{}/CHANGELOG.md)."
        install = "Установка: скачай `BarrensVoice-Setup.exe` и запусти его.\n"
        self.assertEqual(self.release.notes("0.4.1", entries, "v0.4.1"),
                         "### Проверка 0.4.1\n\n- Числа читаются точнее.\n- Новые слова в словаре.\n\n"
                         + link.format("v0.4.1") + "\n\n" + install)
        # a test build: the release it leads to, that release's entry
        self.assertEqual(self.release.notes("0.4.1b2", entries, "v0.4.1-beta.2"),
                         "Тестовая сборка выпуска 0.4.1.\n\n### Проверка 0.4.1\n\n- Числа читаются точнее.\n"
                         "- Новые слова в словаре.\n\n" + link.format("v0.4.1-beta.2") + "\n\n" + install)
        # no entry written for its release yet: that line, the link, the install
        self.assertEqual(self.release.notes("0.4.2b1", entries, "v0.4.2-beta.1"),
                         "Тестовая сборка выпуска 0.4.2.\n\n" + link.format("v0.4.2-beta.1") + "\n\n" + install)
        self.assertIn("/blob/master/CHANGELOG.md", self.release.notes("0.4.1", entries))   # a build without a tag
        # the real one: the version in work's entry, in Russian
        real = self.release.news_entries()
        body = self.release.notes(real[0]["version"], real, "v" + real[0]["version"])
        self.assertTrue(body.startswith("### " + real[0]["title"] + "\n\n- "), body[:80])
        self.assertEqual(body.count("\n- "), len(real[0]["items"]))


if __name__ == "__main__":
    unittest.main()
