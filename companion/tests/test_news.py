"""«Что нового»: news.toml, the one source of the players' news (bv/news.py)."""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bv import news  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
LUAJIT = shutil.which("luajit")


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

    def test_the_archive_carries_the_news(self):
        # the companion writes the addon's «Что нового» from the release's own news.toml
        self.assertIn((ROOT / news.SOURCE, news.SOURCE), self.release.files())


# What LuaJIT reads from a NewsData.lua: each string as <bytes>:<text>, into a file (Windows' stdout would turn
# "\n" into "\r\n"). A script file, not -e: on Windows luajit is a .CMD shim, and cmd mangles quotes in arguments.
READ_BACK = """
dofile(arg[1])
local out = assert(io.open(arg[2], "wb"))
local function put(s) out:write(#s, ":", s) end
local d = BarrensVoiceNewsData
put(d.version)
for _, e in ipairs(d.entries) do
    put(e.version); put(e.date or ""); put(e.kind); put(e.title); put(e.summary)
    out:write(#e.items, "#")
    for _, item in ipairs(e.items) do put(item) end
end
out:close()
"""


def read_back(lua_file: Path) -> dict:
    """NewsData.lua as LuaJIT loads it: {"version", "entries": [{version, date?, kind, title, summary, items}]}."""
    with tempfile.TemporaryDirectory() as d:
        script, got = Path(d) / "read.lua", Path(d) / "out.bin"
        script.write_text(READ_BACK, encoding="utf-8")
        subprocess.run([LUAJIT, str(script), str(lua_file), str(got)], capture_output=True, check=True)
        data, pos = got.read_bytes(), 0

    def text() -> str:
        nonlocal pos
        colon = data.index(b":", pos)
        size = int(data[pos:colon])
        pos = colon + 1 + size
        return data[colon + 1:pos].decode("utf-8")

    def count() -> int:
        nonlocal pos
        mark = data.index(b"#", pos)
        n, pos = int(data[pos:mark]), mark + 1
        return n

    out = {"version": text(), "entries": []}
    while pos < len(data):
        e = {"version": text(), "date": text(), "kind": text(), "title": text(), "summary": text()}
        e["items"] = [text() for _ in range(count())]
        if not e["date"]:
            del e["date"]
        out["entries"].append(e)
    return out


class Companion(unittest.TestCase):
    """The companion writes the entries of its version into the addon as NewsData.lua (bv/news.py)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root, self.addon = Path(tmp.name) / "app", Path(tmp.name) / "BarrensVoice"
        self.root.mkdir()
        self.addon.mkdir()
        self.logged = []

    def program(self, version: str, toml: str) -> None:
        (self.root / "pyproject.toml").write_text(f'[project]\nname = "barrens-voice"\nversion = "{version}"\n',
                                                  encoding="utf-8")
        (self.root / news.SOURCE).write_text(toml, encoding="utf-8")

    def write(self) -> bool:
        return news.write(self.addon, self.logged.append, root=self.root)

    TOML = '''
[[entry]]
version = "0.4.1"
kind = "small"
title = "Кавычки \\"так\\" и обратная \\\\ косая"
summary = "строка с \\\\n внутри, а не перевод"
items = ["Пункт «один».", "Пункт с [[скобками]] и -- не комментарием\\\\"]

[[entry]]
version = "0.4.1b2"
date = "19.11.2026"
kind = "small"
title = "Вторая сборка"
summary = "для тестеров"
items = ["Пункт."]

[[entry]]
version = "0.4.0"
date = "18.11.2026"
kind = "big"
title = "Выпуск"
summary = "много нового"
items = ["Первый.", "Второй."]

[[entry]]
version = "0.3.9"
date = "17.11.2026"
kind = "small"
title = "С разметкой"
summary = "цвет |cffff0000красный|r"
items = ["Пункт."]
'''

    def test_written_for_its_version(self):
        self.program("0.4.1b1", self.TOML)
        self.assertTrue(self.write())
        text = (self.addon / news.FILE).read_text(encoding="utf-8")
        self.assertTrue(text.startswith("-- Written by the Barrens Voice companion app"))
        self.assertIn('    version = "0.4.1b1",\n', text)
        self.assertEqual(self.logged, ["«Что нового» версии 0.4.1b1 записано в аддон: в игре — при входе или после /reload"])
        from bv.logs import level_of
        self.assertEqual(level_of(self.logged[0]), "DEBUG")                  # the details, not the launcher's line
        self.assertFalse(self.write(), "unchanged: not written again")
        self.assertEqual(len(self.logged), 1)
        self.assertEqual([p.name for p in self.addon.iterdir()], [news.FILE])   # no temporary file left
        if LUAJIT:
            got = read_back(self.addon / news.FILE)
            # its release's entry (0.4.1, no date yet) and older ones, not the later test build's own; the entry
            # with the game's markup in it left out
            self.assertEqual(got["version"], "0.4.1b1")
            self.assertEqual([e["version"] for e in got["entries"]], ["0.4.1", "0.4.0"])
            first = got["entries"][0]
            self.assertEqual(first, {"version": "0.4.1", "kind": "small", "title": 'Кавычки "так" и обратная \\ косая',
                                     "summary": "строка с \\n внутри, а не перевод",
                                     "items": ["Пункт «один».", "Пункт с [[скобками]] и -- не комментарием\\"]})
            self.assertEqual(got["entries"][1]["date"], "18.11.2026")
        self.program("0.4.1b2", self.TOML)                                     # the next test build: its own entry
        self.assertTrue(self.write())
        if LUAJIT:
            self.assertEqual([e["version"] for e in read_back(self.addon / news.FILE)["entries"]],
                             ["0.4.1", "0.4.1b2", "0.4.0"])

    @unittest.skipUnless(LUAJIT, "luajit not installed")
    def test_any_text_reads_back(self):
        # what lua_string makes of quotes, backslashes, line breaks and control characters (a digit after \0 too)
        tricky = 'а "б" \\ в\nг\r\tд \x00' + '2 е\x7f ]] [[ -- «ё» \\"'
        entries = [{"version": "0.4.1", "kind": "big", "title": tricky, "summary": "\\", "items": [tricky, '"', ""]}]
        (self.addon / news.FILE).write_text(news.render(entries, "0.4.1"), encoding="utf-8")
        self.assertEqual(read_back(self.addon / news.FILE), {"version": "0.4.1", "entries": entries})

    @unittest.skipUnless(LUAJIT, "luajit not installed")
    def test_the_real_news_read_back(self):
        entries = news.load(ROOT / news.SOURCE)
        working = news.program_version(ROOT)
        self.assertTrue(news.write(self.addon, self.logged.append, root=ROOT))
        self.assertEqual(read_back(self.addon / news.FILE), {"version": working,
                                                             "entries": news.visible(entries, working)})

    def test_what_cannot_be_read_or_written(self):
        from unittest import mock
        self.assertFalse(news.write(None, self.logged.append, root=self.root))          # no addon found
        self.assertFalse(news.write(self.addon / "gone", self.logged.append, root=self.root))
        self.assertEqual(self.logged, [])
        self.assertFalse(self.write())                                                # no news.toml, no pyproject
        self.program("0.4.1", "[[entry]\nbroken")
        self.assertFalse(self.write())
        self.program("0.4.1", self.TOML)
        with mock.patch("bv.paths.os.replace", side_effect=PermissionError("in use")):
            self.assertFalse(self.write())
        from bv.logs import level_of
        self.assertEqual(len(self.logged), 3)
        self.assertTrue(self.logged[0].startswith("не удалось прочитать news.toml: "), self.logged[0])
        self.assertTrue(self.logged[2].startswith("не удалось записать «Что нового» в аддон: in use"), self.logged[2])
        self.assertEqual({level_of(m) for m in self.logged}, {"WARN"})
        self.assertFalse((self.addon / news.FILE).exists())

    def test_the_addon_ships_an_empty_one(self):
        # so the .toc has a file to load before the companion first runs; read before News.lua
        shipped = ROOT / "addon" / "BarrensVoice" / news.FILE
        self.assertIn("\nBarrensVoiceNewsData = nil\n", shipped.read_text(encoding="utf-8"))
        toc = (shipped.parent / "BarrensVoice.toc").read_text(encoding="utf-8")
        self.assertLess(toc.index("\n" + news.FILE + "\n"), toc.index("\nNews.lua\n"))
        from bv.launcher.model import GENERATED
        self.assertIn(news.FILE, GENERATED)                                     # an addon install keeps the companion's


if __name__ == "__main__":
    unittest.main()
