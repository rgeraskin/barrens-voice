"""The dictionary online: what CI publishes, what a companion takes, and how the newer default wins."""
import base64
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "companion"))
sys.path.insert(0, str(ROOT / "tools"))

from bv import online_dictionary as od  # noqa: E402
from bv.dictionary import Dictionary, merged  # noqa: E402

LUAJIT = shutil.which("luajit")


def keys():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    key = Ed25519PrivateKey.generate()
    raw = serialization.Encoding.Raw
    return key, base64.b64encode(key.public_key().public_bytes(raw, serialization.PublicFormat.Raw)).decode()


def published(data: dict, key) -> tuple[bytes, str]:
    raw = json.dumps(data, ensure_ascii=False).encode()
    return raw, base64.b64encode(key.sign(raw)).decode()


def entry(text="кд=кулд+аун\nимба=имб+а\n~(\\d+)\\s*к\\b=\\g<1>000", revision=100, **more):
    return {"format": od.FORMAT, "revision": revision, "date": "2026-11-17",
            "text": text, "renamed": {}, **more}


class Build(unittest.TestCase):
    @unittest.skipUnless(LUAJIT, "luajit not installed")
    def test_from_the_addon(self):
        import dictionary_json
        data = dictionary_json.build(rev=1794864817)
        lua = (ROOT / "addon" / "BarrensVoice" / "Dictionary.lua").read_text(encoding="utf-8")
        self.assertIn(data["text"], lua)
        self.assertIn("кд=", data["text"])
        self.assertEqual((data["format"], data["revision"], data["date"]), (od.FORMAT, 1794864817, "2026-11-16"))
        self.assertIsNone(od.regexes_ok(data["text"]), "the shipped dictionary passes the companions' check")

    def test_bytes_as_signed(self):
        # "\n" only, whatever the system: GitHub serves the bytes git keeps, and the signature is over them
        import dictionary_json
        with tempfile.TemporaryDirectory() as d:
            raw = dictionary_json.write(entry(text="а=б\nв=г"), Path(d) / "dictionary.json").read_bytes()
        self.assertNotIn(b"\r", raw)
        self.assertEqual(json.loads(raw)["text"], "а=б\nв=г")

    @unittest.skipUnless(LUAJIT, "luajit not installed")
    def test_renamed(self):
        # D.RENAMED as the addon builds it, however the table is written
        import dictionary_json
        head = 'local _, ns = ...\nlocal D = {}\nns.Dictionary = D\nD.DEFAULT = [[\nа=б\n]]\n'
        forms = {
            "constructor": 'D.RENAMED = {\n    ["~old\\\\d"] = "~new\\\\d",\n}\n',
            "one line": 'D.RENAMED = { ["~old\\\\d"] = "~new\\\\d" }\n',
            "assignment": 'D.RENAMED = {}\nD.RENAMED["~old\\\\d"] = "~new\\\\d"\n',
            "long strings": 'D.RENAMED = {\n    [ [[~old\\d]] ] = [[~new\\d]],\n}\n',
            "indented close": 'D.RENAMED = {\n    ["~old\\\\d"] = "~new\\\\d",\n    }\n',
        }
        for name, lua in forms.items():
            self.assertEqual(dictionary_json.build(head + lua, rev=1)["renamed"], {"~old\\d": "~new\\d"}, name)
        self.assertEqual(dictionary_json.build(head + "D.RENAMED = {}\nlocal x = {\n    [\"a\"] = \"b\",\n}\n",
                                               rev=1)["renamed"], {})
        with self.assertRaises(SystemExit):                     # a Lua error is no empty table
            dictionary_json.build(head + "D.RENAMED = {\n", rev=1)
        # an entry that became several: one string, the keys joined by "\n" - a map of strings, as older programs read it
        several = 'D.RENAMED = {\n    [ [[~old\\d]] ] = {\n        [[~new\\d]],\n        [[~other]],\n    },\n}\n'
        self.assertEqual(dictionary_json.build(head + several, rev=1)["renamed"], {"~old\\d": "~new\\d\n~other"})


class Load(unittest.TestCase):
    def setUp(self):
        self.key, self.public = keys()

    def load(self, data, **kw):
        raw, sig = published(data, self.key)
        return od.load(raw, sig, self.public, **kw)

    def test_taken(self):
        data, why = self.load(entry())
        self.assertEqual((data["revision"], why), (100, ""))

    def test_refused(self):
        raw, sig = published(entry(), self.key)
        self.assertIn("подпись", od.load(raw.replace(b"100", b"999"), sig, self.public)[1])
        _, other = keys()
        self.assertIn("подпись", od.load(raw, sig, other)[1])
        self.assertIn("формат", self.load(entry(format=od.FORMAT + 1))[1])            # a newer syntax: kept the last
        self.assertIn("ревизии", self.load(entry(revision="100"))[1])
        self.assertIn("ошибкой", self.load(entry(text="~(a=b"))[1])
        self.assertIn("длиннее", self.load(entry(text="~" + "a" * 500 + "=b"))[1])
        # a replacement's group reference the pattern has not: refused before it is published or taken
        self.assertIn("замена", self.load(entry(text="~(\\d+)x=\\2 y"))[1])
        self.assertIn("замена", self.load(entry(text="~(\\d+)x=\\g<n> y"))[1])
        self.assertIsNone(od.regexes_ok("~(\\d+)x=\\g<1>000 [а|б|в]"))

    def test_slow_regex(self):
        # catastrophic backtracking: run in a process of its own and killed, the companion goes on
        why = od.regexes_ok("~(а+)+$=x", timeout=3)
        self.assertIn("медленные", why)


class Online(unittest.TestCase):
    def test_fetch_cache_take(self):
        key, public = keys()
        served = {}

        def serve(data):
            raw, sig = published(data, key)
            served[od.URL + od.FILE], served[od.URL + od.FILE + ".sig"] = raw, sig.encode()
        logged = []
        with tempfile.TemporaryDirectory() as d:
            online = od.Online(Path(d), logged.append, fetch=served.__getitem__, public=public)
            self.assertIsNone(online.cached())                                       # nothing kept yet
            serve(entry(revision=100))
            self.assertEqual(online.fetch_once()["revision"], 100)
            self.assertEqual(online.take()["revision"], 100)
            self.assertIsNone(online.take())                                         # taken once
            self.assertIsNone(online.fetch_once())                                   # the same: not news
            serve(entry(revision=90))
            self.assertIsNone(online.fetch_once())                                   # older: not taken
            serve(entry(revision=120, format=7))
            self.assertIsNone(online.fetch_once())
            self.assertTrue(any("не принят" in m for m in logged))
            again = od.Online(Path(d), logged.append, fetch=served.__getitem__, public=public)
            self.assertEqual(again.cached()["revision"], 100)                        # a start without the network
            (Path(d) / od.FILE).write_text("{}")                                     # spoiled in the data folder
            self.assertIsNone(again.cached())

    def test_spoiled_files_and_a_folder_that_cannot_be_written(self):
        key, public = keys()
        served = {}
        raw, sig = published(entry(revision=100), key)
        served[od.URL + od.FILE], served[od.URL + od.FILE + ".sig"] = raw, sig.encode()
        logged, checked = [], []

        def check(text):
            checked.append(text)
            return None
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / od.FILE).write_bytes(raw)
            (Path(d) / (od.FILE + ".sig")).write_bytes(b"\xff\xfe not ascii")   # a non-ASCII byte: refused, no exception
            self.assertIsNone(od.Online(Path(d), logged.append, public=public).cached())
            blocked = Path(d) / "file"
            blocked.write_text("")                                                   # the data folder cannot be made
            online = od.Online(blocked / "data", logged.append, fetch=served.__getitem__, public=public, check=check)
            self.assertEqual(online.fetch_once()["revision"], 100)                   # used all the same
            self.assertTrue(any("не сохранён" in m for m in logged))
            self.assertEqual(len(checked), 1)
            self.assertIsNone(online.fetch_once())                                   # the same revision again:
            self.assertEqual(len(checked), 1)                                        # not checked again

    def test_the_thread_lives_on(self):
        # an exception in a fetch (here: thrown by the fetch itself) is logged; the hourly loop goes on
        import threading
        logged, done = [], threading.Event()

        def log(message):
            logged.append(message)
            done.set()
        online = od.Online(Path(tempfile.gettempdir()), log)
        online.fetch_once = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
        thread = online.start(every=3600)
        self.assertTrue(done.wait(5))
        self.assertTrue(thread.is_alive())
        self.assertIn("boom", logged[0])

    def test_not_an_object(self):
        key, public = keys()
        raw = json.dumps([1, 2]).encode()
        self.assertIsNone(od.load(raw, base64.b64encode(key.sign(raw)).decode(), public)[0])

    def test_offline(self):
        logged = []

        def down(url):
            raise OSError("no network")
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(od.Online(Path(d), logged.append, fetch=down).fetch_once())
        self.assertTrue(any("не скачался" in m for m in logged))


class Newer(unittest.TestCase):
    def dictionary(self, folder: Path, revision: int) -> Dictionary:
        (folder / "Dictionary.lua").write_text(f"D.DEFAULT = [[\nкд=кд аддона\n]]\nD.REVISION = {revision}\n",
                                               encoding="utf-8")
        d = Dictionary({}, lambda m: None, folder)
        d.refresh()
        return d

    def test_the_newer_default_wins(self):
        with tempfile.TemporaryDirectory() as t:
            d = self.dictionary(Path(t), 100)
            self.assertEqual(d.apply_words("кд"), "\x02кд аддона\x03")
            d.use_online(entry(text="кд=кд онлайн", revision=200))
            self.assertEqual(d.apply_words("кд"), "\x02кд онлайн\x03")
            d = self.dictionary(Path(t), 300)                                        # a newer addon came
            d.use_online(entry(text="кд=кд онлайн", revision=200))
            self.assertEqual(d.apply_words("кд"), "\x02кд аддона\x03")

    def test_renamed(self):
        default = "~new=x\nа=б"
        self.assertEqual(merged(default, "", {"~old": "~new"}), ["~new=x", "а=б"])
        self.assertEqual(merged(default, "!~old=y", {"~old": "~new"}), ["а=б"])      # deleted the old: no new
        self.assertEqual(merged(default, "~old=mine", {"~old": "~new"}), ["а=б", "~old=mine"])
        # an entry that became several (dictionary.json joins the keys by "\n"): none of them
        default = "~a=x\n~b=y\nа=б"
        self.assertEqual(merged(default, "!~old=y", {"~old": "~a\n~b"}), ["а=б"])
        self.assertEqual(merged(default, "~old=mine", {"~old": ["~a", "~b"]}), ["а=б", "~old=mine"])
        self.assertEqual(merged(default, "", {"~old": "~a\n~b"}), ["~a=x", "~b=y", "а=б"])

    def test_removed_from_the_default(self):
        # a newer default without an entry: gone for who did not touch it, kept for who changed it
        # (their line is their own), and a player's "deleted" mark on it no longer matters
        old_default, new_default = "кд=кулд+аун\nимба=имб+а", "кд=кулд+аун"
        self.assertEqual(merged(old_default, ""), ["кд=кулд+аун", "имба=имб+а"])
        self.assertEqual(merged(new_default, ""), ["кд=кулд+аун"])
        self.assertEqual(merged(new_default, "имба=имба"), ["кд=кулд+аун", "имба=имба"])
        self.assertEqual(merged(new_default, "!имба=имб+а"), ["кд=кулд+аун"])

    def test_cleared_from_the_addon_when_off(self):
        shipped = (ROOT / "addon" / "BarrensVoice" / "DictionaryOnline.lua").read_text(encoding="utf-8")
        self.assertEqual(od.EMPTY_LUA, shipped)
        with tempfile.TemporaryDirectory() as t:
            self.assertFalse(od.clear_addon(Path(t), print))                          # none there: nothing to do
            od.write_addon(Path(t), entry(), print)
            self.assertTrue(od.clear_addon(Path(t), print))
            self.assertEqual((Path(t) / "DictionaryOnline.lua").read_text(encoding="utf-8"), shipped)
            self.assertFalse(od.clear_addon(Path(t), print))                          # as shipped: not written
            # written in place, a game reading it at that moment could get half a file; a failed swap keeps
            # the old one whole
            from unittest import mock
            od.write_addon(Path(t), entry(), print)
            before = (Path(t) / "DictionaryOnline.lua").read_text(encoding="utf-8")
            logged = []
            with mock.patch("bv.paths.os.replace", side_effect=PermissionError("in use")):
                self.assertFalse(od.clear_addon(Path(t), logged.append))
            self.assertEqual((Path(t) / "DictionaryOnline.lua").read_text(encoding="utf-8"), before)
            self.assertEqual(logged, ["словарь онлайн: не убран из аддона (in use)"])
            self.assertEqual([p.name for p in Path(t).iterdir()], ["DictionaryOnline.lua"])

    def test_written_into_the_addon(self):
        with tempfile.TemporaryDirectory() as t:
            data = entry(text="кд=кулд+аун\n~a]]b=c", renamed={'~o"ld': "~new"})
            self.assertTrue(od.write_addon(Path(t), data, print))
            self.assertFalse(od.write_addon(Path(t), data, print))                    # unchanged: not written
            self.assertFalse(od.write_addon(Path(t) / "missing", data, print))
            if LUAJIT:
                # a script file, not -e: on Windows luajit is a .CMD shim, and cmd mangles quotes in arguments
                script = Path(t) / "check.lua"
                script.write_text('dofile(arg[1]); local o = BarrensVoiceDictionaryOnline; '
                                  'io.write(o.revision, "|", o.renamed[\'~o"ld\'], "|", o.text)', encoding="utf-8")
                out = subprocess.run([LUAJIT, str(script), str(Path(t) / "DictionaryOnline.lua")],
                                     capture_output=True, check=True).stdout.decode()
                # Windows' stdout writes "\n" as "\r\n"; the long string itself has "\n" (Lua normalises line ends in it)
                self.assertEqual(out.replace("\r\n", "\n"), "100|~new|" + data["text"])


class Release(unittest.TestCase):
    def test_revision_in_the_release(self):
        import release
        self.assertGreater(release.dictionary_revision(), 1700000000)
        lua = (ROOT / "addon" / "BarrensVoice" / "Dictionary.lua").read_text(encoding="utf-8")
        self.assertRegex(lua, r"(?m)^D\.REVISION = 0$")                              # what release.py replaces
