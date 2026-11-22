"""The voice bank from the game client: reading the storage, choosing lines, the cache."""
import json
import re
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bv import casc, gamevoices  # noqa: E402


def root_v2(blocks):
    """A root table (version 2) of blocks [(locale, [(fdid, ckey)])], without name hashes."""
    out = b"TSFM" + struct.pack("<IIII", 0x18, 2, 99, 0) + b"\0" * 4
    for locale, files in blocks:
        out += struct.pack("<IIII", len(files), locale, 0x10000000, 0) + b"\0"
        prev = -1
        for fdid, _ in files:
            out += struct.pack("<i", fdid - prev - 1)
            prev = fdid
        out += b"".join(ck for _, ck in files)
    return out


class Storage(unittest.TestCase):
    def test_blte(self):
        self.assertEqual(casc.blte(b"BLTE" + b"\0\0\0\0" + b"Nhello"), b"hello")
        z = b"Z" + zlib.compress(b"world")
        self.assertEqual(casc.blte(b"BLTE" + b"\0\0\0\0" + z), b"world")
        # two chunks, with a chunk table
        chunks = [b"Nab", b"Z" + zlib.compress(b"cd")]
        table = b"".join(struct.pack(">II", len(c), 2) + b"\0" * 16 for c in chunks)
        header = 12 + len(table)
        data = b"BLTE" + struct.pack(">I", header) + b"\x0f" + (2).to_bytes(3, "big") + table + b"".join(chunks)
        self.assertEqual(casc.blte(data), b"abcd")
        with self.assertRaises(ValueError):
            casc.blte(b"BLTE" + b"\0\0\0\0" + b"Esecret")

    def test_a_block_cut_short_is_a_missing_file(self):
        # a truncated BLTE block raised struct.error, which ended the whole bank instead of one file
        blocks = {b"A" * 16: b"BLTE\0\0", b"B" * 16: b"BLTE" + b"\0\0\0\x20" + b"\x0f\0\0\x02" + b"\0" * 8,
                  b"C" * 16: b"BLTE\0\0\0\0Nfine"}

        class Fake(casc.Storage):
            def __init__(self):
                pass

            def ekeys_for(self, ckeys):
                return {ck: ck for ck in ckeys}

            def read_ekey(self, ekey):
                return casc.blte(blocks[ekey])
        self.assertEqual(Fake().read_ckeys(list(blocks)), {b"C" * 16: b"fine"})

    def test_root_keeps_only_wanted(self):
        ru, en = casc.LOCALES["ruRU"], casc.LOCALES["enUS"]
        raw = root_v2([(en, [(10, b"E" * 16), (12, b"F" * 16)]), (ru, [(10, b"R" * 16)])])
        self.assertEqual(casc.parse_root(raw, {10}), {10: [(en, b"E" * 16), (ru, b"R" * 16)]})
        self.assertEqual(casc.parse_root(raw, {12, 99}), {12: [(en, b"F" * 16)]})

    def test_missing_file_from_the_other_game(self):
        # retail lists a file it has not downloaded; Forever holds the same content key on its disk
        ru = casc.LOCALES["ruRU"]

        class Fake(casc.Storage):
            def __init__(self, root_entries, local):
                self.entries, self.local = root_entries, local
            def root(self, wanted):
                return {f: v for f, v in self.entries.items() if f in wanted}
            def read_ckeys(self, ckeys):
                return {ck: self.local[ck] for ck in ckeys if ck in self.local}
        retail = Fake({1: [(ru, b"A" * 16)], 2: [(ru, b"B" * 16)]}, {b"A" * 16: b"oggA"})
        forever = Fake({}, {b"B" * 16: b"oggB"})
        self.assertEqual(retail.read_files({1, 2}), {1: b"oggA"})
        self.assertEqual(retail.read_files({1, 2}, others=[forever]), {1: b"oggA", 2: b"oggB"})
        self.assertEqual((retail.borrowed, retail.missing), (1, []))   # one taken from Forever, none on no disk

    def test_product_of(self):
        with tempfile.TemporaryDirectory() as d:
            flavor = Path(d) / "_forever_"
            flavor.mkdir()
            self.assertEqual(casc.product_of(flavor), "wowf")            # the usual one
            (flavor / ".flavor.info").write_text("Product Flavor!STRING:0\nwowx\n", encoding="utf-8")
            self.assertEqual(casc.product_of(flavor), "wowx")


class Choosing(unittest.TestCase):
    def test_plausible(self):
        self.assertTrue(gamevoices.plausible("Недостаточно маны.", 1.4))
        self.assertFalse(gamevoices.plausible("Добро пожаловать в Казахстан!", 0.6))   # a shout, too short
        self.assertFalse(gamevoices.plausible("Добро пожаловать в Казахстан!", 1.0))   # too fast for the time
        self.assertFalse(gamevoices.plausible("Продолжение следует...", 2.0))
        self.assertFalse(gamevoices.plausible("Thank you.", 1.0))
        self.assertFalse(gamevoices.plausible("Ха-ха-ха!", 1.5))

    def test_choose(self):
        lines = [
            {"text": "Мне это не по силам.", "seconds": 1.8, "priority": 1},
            {"text": "Это ещё не готово.", "seconds": 1.6, "priority": 1},
            {"text": "Чем могу помочь?", "seconds": 1.5, "priority": 1},
            {"text": "Ты уверен?", "seconds": 1.0, "priority": 1},
            {"text": "Слишком далеко.", "seconds": 1.4, "priority": 1},
            {"text": "Думаешь, легко быть зелёным? Это ведь от орков пошло!", "seconds": 4.0, "priority": 3},
        ]
        picked = gamevoices.choose(lines)
        self.assertLessEqual(len(picked), gamevoices.MAX_LINES)
        self.assertLessEqual(sum(x["seconds"] for x in picked), gamevoices.TARGET[1])
        self.assertLessEqual(sum(x["text"].endswith("?") for x in picked), 1)          # one question at most
        self.assertFalse(picked[-1]["text"].endswith("?"))                             # ends with a statement
        self.assertTrue(all(x["priority"] == 1 for x in picked))                       # calm lines first
        self.assertEqual(gamevoices.joined_text([{"text": "«Привет»"}, {"text": "Пока!"}]), "Привет. Пока!")


class Cache(unittest.TestCase):
    def test_kept_while_the_build_is_the_same(self):
        with tempfile.TemporaryDirectory() as d:
            install = Path(d) / "World of Warcraft"
            (install / "Data").mkdir(parents=True)
            (install / "_forever_").mkdir()
            info = install / ".build.info"
            head = "Branch!STRING:0|Active!DEC:1|Build Key!HEX:16|Version!STRING:0|Product!STRING:0\n"
            info.write_text(head + "eu|1|" + "a" * 32 + "|1.15.8|wowf\n", encoding="utf-8")
            config = {"wow_dir": str(install / "_forever_"), "voice_shifts": [1.5]}
            out = Path(d) / "voices"
            self.assertTrue(gamevoices.stale(config, out))                             # no bank yet
            stamp = gamevoices._stamp(config, [1.5])
            out.mkdir()
            slot = {"id": "orc-male", "base": "orc-male", "race": "orc", "sex": "male", "shift": 0.0,
                    "path": str(out / "orc-male.wav"), "text": "Текст.", "speech": 2.0}
            (out / "orc-male.wav").write_bytes(b"RIFF")
            (out / "bank.json").write_text(json.dumps({"stamp": stamp, "slots": [slot]}), encoding="utf-8")
            self.assertFalse(gamevoices.stale(config, out))
            slots = gamevoices.build(config, out, print, checker=None)                 # no Whisper needed
            self.assertEqual([s.id for s in slots], ["orc-male"])
            info.write_text(head + "eu|1|" + "b" * 32 + "|1.15.9|wowf\n", encoding="utf-8")
            self.assertTrue(gamevoices.stale(config, out))                             # the game was updated
            with self.assertRaises(RuntimeError):
                gamevoices.build(config, out, print, checker=None)                     # and Whisper is needed

    def test_incomplete_made_again_when_the_storage_grows(self):
        # retail before its background download is done: some voice files are on no disk yet
        with tempfile.TemporaryDirectory() as d:
            install = Path(d) / "World of Warcraft"
            (install / "Data" / "data").mkdir(parents=True)
            (install / "_forever_").mkdir()
            head = "Branch!STRING:0|Active!DEC:1|Build Key!HEX:16|Version!STRING:0|Product!STRING:0\n"
            (install / ".build.info").write_text(head + "eu|1|" + "a" * 32 + "|1.15.8|wowf\n", encoding="utf-8")
            config = {"wow_dir": str(install / "_forever_"), "voice_shifts": []}
            out = Path(d) / "voices"
            out.mkdir()
            stamp = gamevoices._stamp(config, [])
            slot = {"id": "orc-male", "base": "orc-male", "race": "orc", "sex": "male", "shift": 0.0,
                    "path": str(out / "orc-male.wav"), "text": "Текст.", "speech": 2.0}
            (out / "orc-male.wav").write_bytes(b"RIFF")
            archive = install / "Data" / "data" / "data.000"
            archive.write_bytes(b"x" * 1000)
            for gap, stale in ((None, False), ({"missing_files": 3, "data_size": 1000}, False)):
                bank = {"stamp": stamp, "slots": [slot]}
                if gap:
                    bank["incomplete"] = gap
                (out / "bank.json").write_text(json.dumps(bank), encoding="utf-8")
                self.assertEqual(gamevoices.stale(config, out), stale)
            with open(archive, "r+b") as f:                    # the download goes on: the storage grows
                f.truncate(1000 + gamevoices.GROWN + 1)
            self.assertTrue(gamevoices.stale(config, out), "incomplete and grown: made again")
            (out / "bank.json").write_text(json.dumps({"stamp": stamp, "slots": [slot]}), encoding="utf-8")
            self.assertFalse(gamevoices.stale(config, out), "a complete bank stays, whatever the storage does")


    def test_damaged_bank_is_made_again(self):
        # bank.json cut short (the companion killed while writing it), of another shape, or a clip gone:
        # made again, not an error that leaves the race voices off for good
        with tempfile.TemporaryDirectory() as d:
            install = Path(d) / "World of Warcraft"
            (install / "Data").mkdir(parents=True)
            (install / "_forever_").mkdir()
            head = "Branch!STRING:0|Active!DEC:1|Build Key!HEX:16|Version!STRING:0|Product!STRING:0\n"
            (install / ".build.info").write_text(head + "eu|1|" + "a" * 32 + "|1.15.8|wowf\n", encoding="utf-8")
            config = {"wow_dir": str(install / "_forever_"), "voice_shifts": []}
            out = Path(d) / "voices"
            out.mkdir()
            stamp = gamevoices._stamp(config, [])
            clip = out / "orc-male.wav"
            clip.write_bytes(b"RIFF")
            slot = {"id": "orc-male", "base": "orc-male", "race": "orc", "sex": "male", "shift": 0.0,
                    "path": str(clip), "text": "Текст.", "speech": 2.0}
            whole = json.dumps({"stamp": stamp, "slots": [slot] * 20})
            (out / "bank.json").write_text(whole, encoding="utf-8")
            self.assertFalse(gamevoices.stale(config, out))
            for broken in (whole[:len(whole) // 2], "[]", json.dumps({"stamp": stamp}),
                           json.dumps({"stamp": stamp, "slots": [{"id": "orc-male"}]}),
                           json.dumps({"stamp": stamp, "slots": ["x"]}),
                           json.dumps({"stamp": stamp, "slots": [{**slot, "path": 5}]}),     # raised past load's try
                           json.dumps({"stamp": stamp, "slots": [{**slot, "path": None}]})):
                (out / "bank.json").write_text(broken, encoding="utf-8")
                self.assertTrue(gamevoices.stale(config, out), broken[:40])
            (out / "bank.json").write_text(whole, encoding="utf-8")
            clip.unlink()
            self.assertTrue(gamevoices.stale(config, out), "a clip gone")


class Building(unittest.TestCase):
    """build()'s main path with the game's storage, the decoder and Whisper faked: lines chosen,
    joined, heard back, the shifted copies, the manifest."""

    def test_bank_made_and_kept(self):
        from unittest import mock

        import numpy as np
        table = {"orc-male": {"race": "orc", "sex": "male", "files": [[i, "error", 1] for i in range(4)]}}

        class Store:
            def __init__(self, *_):
                self.missing, self.borrowed = [], 0

            def read_files(self, wanted, *_):
                return {f: b"ogg" for f in wanted}

        class Checker:
            def transcribe(self, x, rate):
                return "Мне это не по силам."

            def score(self, x, rate, text):
                return 1.0, text
        tone = (np.sin(np.arange(48000) / 24000 * 2 * np.pi * 150) * 0.3).astype("float32")   # 2 s
        stamp = {"install": "x", "product": "wowf"}
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(gamevoices, "_stamp", return_value=stamp), \
                mock.patch.object(gamevoices, "voices_for", return_value=table), \
                mock.patch.object(gamevoices, "other_storages", return_value=[]), \
                mock.patch.object(gamevoices, "_decode", return_value=tone), \
                mock.patch.object(casc, "Storage", Store):
            out = Path(d) / "voices"
            slots = gamevoices.build({"voice_shifts": [-1.5, 1.5]}, out, lambda *a: None, Checker())
            self.assertEqual([s.id for s in slots], ["orc-male", "orc-male^-1.5", "orc-male^+1.5"])
            self.assertEqual(slots[0].text, "Мне это не по силам. Мне это не по силам. Мне это не по силам.")
            self.assertEqual(slots[0].speech, 6.0)                          # three lines of 2 s
            self.assertGreater(slots[1].speech, slots[0].speech)            # lower: slower
            self.assertEqual(sorted(p.name for p in out.iterdir()),
                             ["bank.json", "orc-male.wav", "orc-male_+1.5.wav", "orc-male_-1.5.wav"])
            self.assertEqual(gamevoices.load(out, stamp), slots)            # kept: not made again


class Picks(unittest.TestCase):
    """voice_picks.yaml: a voice's lines chosen by ear (the voice lab), taken as they are, in their order."""

    def test_the_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "picks.yaml"
            self.assertEqual(gamevoices.load_picks(path), {})                     # no file: every voice chosen
            path.write_text("voices:\n  troll-female/old:\n    - 562826  # торговля\n    # - 562829  # прощание\n"
                            "    - 562820\n  orc-male:\n    # - 1\n", encoding="utf-8")
            self.assertEqual(gamevoices.load_picks(path), {"troll-female/old": [562826, 562820], "orc-male": []})

    def test_lines_with_their_texts(self):
        text = 'voices:\n  orc-male:\n    - 5\n    - 6: "Это моя реплика: вторая."\n    - 7:\n    # - 8: "нет"\n'
        self.assertEqual(gamevoices.lines_of(text), {"orc-male": [(5, None), (6, "Это моя реплика: вторая."), (7, None)]})
        self.assertEqual(gamevoices.picks_of(text), {"orc-male": [5, 6, 7]})
        with self.assertRaises(ValueError):
            gamevoices.lines_of("voices:\n  orc-male:\n    - {5: a, 6: b}\n")

    def test_the_players_file_names_real_lines(self):
        table = json.loads(gamevoices.TABLE.read_text(encoding="utf-8"))["voices"]
        for voice, files in gamevoices.load_picks().items():
            self.assertIn(voice, table)
            self.assertLessEqual(set(files), {f[0] for f in table[voice]["files"]}, voice)

    def test_a_picked_text_is_taken_as_written(self):
        # the file's text: the clip's, not asked of Whisper; a line without one is heard as before
        from unittest import mock

        import numpy as np
        table = {"orc-male": {"race": "orc", "sex": "male", "files": [[i, "error", 1] for i in range(1, 4)]}}
        heard = []

        class Store:
            def __init__(self, *_):
                self.missing, self.borrowed = [], 0

            def read_files(self, wanted, *_):
                return {f: f for f in wanted}

        class Checker:
            def transcribe(self, x, rate):
                heard.append(int(x[0]))
                return "Так услышал Whisper."

            def score(self, x, rate, text):
                return 0.0, ""
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(gamevoices, "_stamp", return_value={"install": "x", "product": "wowf"}), \
                mock.patch.object(gamevoices, "voices_for", return_value=table), \
                mock.patch.object(gamevoices, "load_lines",
                                  return_value={"orc-male": [(2, "Поправлено руками."), (1, None), (3, "Третья.")]}), \
                mock.patch.object(gamevoices, "other_storages", return_value=[]), \
                mock.patch.object(gamevoices, "_decode", side_effect=lambda f: np.full(48000, f, dtype="float32")), \
                mock.patch.object(casc, "Storage", Store):
            slots = gamevoices.build({}, Path(d) / "voices", lambda *a: None, Checker())
        self.assertEqual(slots[0].text, "Поправлено руками. Так услышал Whisper. Третья.")
        self.assertEqual(heard, [1])

    def test_picks_change_the_stamp(self):
        from unittest import mock
        with mock.patch.object(gamevoices, "find_game", return_value=(Path("x"), Path("x/_forever_"))), \
                mock.patch("bv.casc.build_info", return_value={"Build Key": "b"}), \
                mock.patch("bv.casc.product_of", return_value="wowf"):
            with mock.patch.object(gamevoices, "load_lines", return_value={}):
                before = gamevoices._stamp({}, [])
            with mock.patch.object(gamevoices, "load_lines", return_value={"vulpera-male": [(1, None)]}):
                other_game = gamevoices._stamp({}, [])            # a retail race's pick: not Forever's bank
            with mock.patch.object(gamevoices, "load_lines", return_value={"orc-male": [(1, None)]}):
                after = gamevoices._stamp({}, [])
        with mock.patch.object(gamevoices, "find_game", return_value=(Path("x"), Path("x/_forever_"))), \
                mock.patch("bv.casc.build_info", return_value={"Build Key": "b"}), \
                mock.patch("bv.casc.product_of", return_value="wowf"), \
                mock.patch.object(gamevoices, "load_lines", return_value={"orc-male": [(1, "Текст.")]}):
            with_text = gamevoices._stamp({}, [])
        self.assertNotEqual(with_text, after)                    # a text corrected: the bank is made again
        self.assertNotIn("picks", before)                        # no picks: the bank as before, not made again
        self.assertEqual(other_game, before)
        self.assertNotEqual(before, after)                       # the bank is made again with the new lines

    def test_bank_from_picked_lines(self):
        from unittest import mock

        import numpy as np
        table = {"orc-male": {"race": "orc", "sex": "male", "files": [[i, "error", 1] for i in range(4)]},
                 "orc-female": {"race": "orc", "sex": "female", "files": [[i, "error", 1] for i in range(10, 14)]}}
        texts = {0: "Ноль.", 1: "Один.", 2: "Два.", 3: "Три."}
        heard = []

        class Store:
            def __init__(self, *_):
                self.missing, self.borrowed = [], 0

            def read_files(self, wanted, *_):
                return {f: f for f in wanted}

        class Checker:
            def transcribe(self, x, rate):
                heard.append(int(x[0]))
                return texts.get(int(x[0]), "Нет.")

            def score(self, x, rate, text):
                return 0.0, ""                                # by ear: taken though Whisper disagrees

        def decode(fdid):
            return np.full(48000, fdid, dtype="float32")      # 2 s, its id in the samples
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(gamevoices, "_stamp", return_value={"install": "x", "product": "wowf"}), \
                mock.patch.object(gamevoices, "voices_for", return_value=table), \
                mock.patch.object(gamevoices, "load_lines",
                                  return_value={"orc-male": [(3, None), (1, None)], "orc-female": []}), \
                mock.patch.object(gamevoices, "other_storages", return_value=[]), \
                mock.patch.object(gamevoices, "_decode", side_effect=decode), \
                mock.patch.object(casc, "Storage", Store):
            slots = gamevoices.build({}, Path(d) / "voices", lambda *a: None, Checker())
        self.assertEqual([s.id for s in slots], ["orc-male"])                  # orc-female left out
        self.assertEqual(slots[0].text, "Три. Один.")                         # those lines, in that order
        self.assertEqual(slots[0].speech, 4.0)
        self.assertEqual(sorted(heard), [1, 3])                               # only they were heard

    def test_the_lab_file_reads_back(self):
        from bv import voicelab
        heard = [{"fdid": 5, "tag": "farewell", "text": "Пока-пока.", "seconds": 0.6, "priority": 1, "usable": False},
                 {"fdid": 3, "tag": "vendor", "text": "У меня отличный товар.", "seconds": 1.6, "priority": 1,
                  "usable": True},
                 {"fdid": 7, "tag": "pissed", "text": "Отстань!", "seconds": 1.1, "priority": 3, "usable": True}]
        text = voicelab.lab_text([("troll-female/old", heard, [7, 3]), ("orc-male", heard, [])], "Тест, «да».")
        self.assertIn('    # - 5: "Пока-пока."  # прощание, 0.6 с (не годится)', text)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "voices.yaml"
            path.write_text(text, encoding="utf-8")
            self.assertEqual(gamevoices.load_picks(path), {"troll-female/old": [7, 3], "orc-male": []})
            self.assertEqual(voicelab.read_lab(path)[1], "Тест, «да».")
            # one voice made again (--only): the others' blocks stay as the player edited them
            edited = text.replace("    - 7:", "    # - 7:")
            merged = voicelab.merge_lab(edited, [("orc-male", heard, [3])], "Тест, «да».")
            path.write_text(merged, encoding="utf-8")
            self.assertEqual(gamevoices.load_picks(path), {"troll-female/old": [3], "orc-male": [3]})

    def test_any_text_reads_back_as_written(self):
        from bv import voicelab
        odd = ['Он сказал: "стой" \\ — и всё.', "а\x85б", "а\x7fб\x9f", "а\u2028б", "а\tб", "а\ud800б"]
        heard = [{"fdid": n, "tag": "vendor", "text": s, "seconds": 2.0, "priority": 1, "usable": True}
                 for n, s in enumerate(odd, 1)]
        text = voicelab.lab_text([("orc-male", heard, list(range(1, len(odd) + 1)))], odd[0])
        self.assertEqual(gamevoices.lines_of(text)["orc-male"], [(n, s.strip()) for n, s in enumerate(odd, 1)])
        with tempfile.TemporaryDirectory() as d:                         # the test text too
            (Path(d) / "voices.yaml").write_text(voicelab.lab_text([], odd[2]), encoding="utf-8")
            self.assertEqual(voicelab.read_lab(Path(d) / "voices.yaml")[1], odd[2])

    def test_texts_yaml_would_read_otherwise_are_refused(self):
        from bv import voicelab
        for item in ("- 5: yes", "- 5: 1.50", "- 5: 7"):
            with self.assertRaises(ValueError) as stop:
                voicelab.lines_or_stop(f"voices:\n  orc-male:\n    {item}\n", "voices.yaml")
            self.assertIn("в кавычках", str(stop.exception))
        with self.assertRaises(ValueError) as stop:
            voicelab.lines_or_stop("voices:\n  orc-male:\n    - 5: Нет: да\n", "voices.yaml")
        self.assertIn("не читается как YAML", str(stop.exception))
        with self.assertRaises(ValueError) as stop:                       # YAML, but two lines in one item
            voicelab.lines_or_stop("voices:\n  orc-male:\n    - {5: а, 6: б}\n", "voices.yaml")
        self.assertNotIn("не читается как YAML", str(stop.exception))
        self.assertIn("одна реплика", str(stop.exception))
        for item in ("- true", "- 1.5", "- {1.5: а}"):                       # no file of the game
            with self.assertRaises(ValueError) as stop:
                voicelab.lines_or_stop(f"voices:\n  orc-male:\n    {item}\n", "voices.yaml")
            self.assertIn("не номер файла игры", str(stop.exception))
        # an empty text is no text, a text's edges are not its own
        self.assertEqual(gamevoices.lines_of('voices:\n  a:\n    - 5: "  "\n    - 6: " Да. "\n'),
                         {"a": [(5, None), (6, "Да.")]})

    def test_the_lab_run(self):
        # every line in all/, the clip's in used/, the clip, the file; run again from the edited file: the lines
        # chosen by ear, no line heard by Whisper twice
        from unittest import mock

        import numpy as np
        from bv import voicelab
        table = {"troll-female/old": {"race": "troll", "sex": "female", "files": [[i, "vendor", 1] for i in range(1, 5)]}}
        texts = {1: "Пусть духи хранят тебя.", 2: "У меня отличный товар.", 3: "Чего ищешь?", 4: "Пока-пока."}
        asked = []

        class Store:
            def __init__(self, *_):
                pass

            def read_files(self, wanted, *_):
                return {f: f for f in wanted}

        class Checker:
            def __init__(self, *_):
                pass

            def load(self):
                return True

            def transcribe(self, x, rate):
                asked.append(int(x[0]))
                return texts[int(x[0])]

            def score(self, x, rate, text):
                return 1.0, text
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(gamevoices, "_stamp", return_value={"install": "x", "product": "wowf"}), \
                mock.patch.object(gamevoices, "voices_for", return_value=table), \
                mock.patch.object(gamevoices, "PICKS", Path(d) / "none.yaml"), \
                mock.patch.object(gamevoices, "other_storages", return_value=[]), \
                mock.patch.object(gamevoices, "_decode", side_effect=lambda f: np.full(48000, f, dtype="float32")), \
                mock.patch.object(casc, "Storage", Store), \
                mock.patch("bv.whisper_onnx.OnnxChecker", Checker), \
                mock.patch("bv.f5engine.preload"):
            out = Path(d) / "lab"
            self.assertEqual(voicelab.run({}, Path(d), out, lambda *a: None, f5=False), 0)
            voice = out / "troll-female" / "old"
            self.assertEqual(sorted(p.name for p in (voice / "all").iterdir()),
                             ["1 торговля Пусть духи хранят тебя.wav", "2 торговля У меня отличный товар.wav",
                              "3 торговля (не годится) Чего ищешь.wav",            # too few letters a second
                              "4 торговля (не годится) Пока-пока.wav"])
            self.assertTrue((voice / "sample.wav").is_file() and (voice / "sample.txt").is_file())
            used = gamevoices.load_picks(out / "voices.yaml")["troll-female/old"]
            self.assertEqual(len(list((voice / "used").iterdir())), len(used))
            # by ear: only «Пусть духи…» and «У меня отличный товар.», in that order
            lab = (out / "voices.yaml").read_text(encoding="utf-8")
            lab = re.sub(r"(?m)^    - ", "    # - ", lab).replace("    # - 1:", "    - 1:").replace("    # - 2:", "    - 2:")
            (out / "voices.yaml").write_text(lab, encoding="utf-8")
            asked.clear()
            voicelab.run({}, Path(d), out, lambda *a: None, f5=False)
            self.assertEqual(asked, [])                                          # transcripts.json
            self.assertEqual(sorted(p.name for p in (voice / "used").iterdir()),
                             ["1 1 Пусть духи хранят тебя.wav", "2 2 У меня отличный товар.wav"])
            self.assertEqual((voice / "sample.txt").read_text(encoding="utf-8").strip(),
                             "Пусть духи хранят тебя. У меня отличный товар.")
            self.assertEqual(gamevoices.load_picks(out / "voices.yaml"), {"troll-female/old": [1, 2]})

    def test_the_remote_task(self):
        # mise run voicelab: the code with its runner; --pick: the lab's file under the players' file's header
        import io
        import tarfile
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
        import voicelab_remote
        with tarfile.open(fileobj=io.BytesIO(voicelab_remote.packed())) as tar:
            names = tar.getnames()
        self.assertIn("labrun.py", names)
        self.assertIn("bv/voicelab.py", names)
        self.assertFalse(any("__pycache__" in n for n in names))
        lab = "# lab\n# notes\n\ntest_text: \"x\"\n\nvoices:\n  orc-male:\n    - 1  # ошибка\n" \
              "  troll-female/old:\n    - 4  # торговля\n    - 3  # торговля\n"
        empty = voicelab_remote.PICKS_HEAD + "\nvoices: {}\n"
        self.assertTrue(gamevoices.PICKS.read_text(encoding="utf-8").startswith(voicelab_remote.PICKS_HEAD))
        # only what differs from the automatic choice goes in: orc-male [1] is the automatic one
        picks = voicelab_remote.lab_to_picks(lab, empty, {"orc-male": [1], "troll-female/old": [3, 4]})
        self.assertTrue(picks.startswith(voicelab_remote.PICKS_HEAD) and "# lab" not in picks)
        self.assertEqual(gamevoices.picks_of(picks), {"troll-female/old": [4, 3]})
        # the lab wins for its voices (K2); one back to its automatic choice leaves the file; others stay
        players = voicelab_remote.PICKS_HEAD + "\nvoices:\n  orc-male:\n    - 9\n  troll-female/old:\n    - 7\n" \
                                                "  undead-male:\n    - 5\n"
        merged = voicelab_remote.lab_to_picks(lab, players, {"orc-male": [2], "troll-female/old": [4, 3]})
        self.assertEqual(gamevoices.picks_of(merged), {"orc-male": [1], "undead-male": [5]})
        # a hand-written voice of another shape is kept, or the task stops: never lost silently
        for odd in ("voices:\n  troll-female/old:\n    - 7\n  zandalari-male: []\n",
                    "voices:\n  troll-female/old:\n    - 7\n  zandalari-male: [5, 6]\n",
                    "voices:\n  troll-female/old:\n    - 7\n  zandalari-male:  # by ear\n    - 5\n",
                    "voices: {undead-male: [1, 2]}\n", "voices:\n  zandalari-male: [5, 6]\n"):
            try:
                out = voicelab_remote.lab_to_picks(lab, odd, {"orc-male": [2], "troll-female/old": [3]})
            except ValueError:
                continue
            self.assertEqual(gamevoices.picks_of(out),
                             {**gamevoices.picks_of(odd), "orc-male": [1], "troll-female/old": [4, 3]}, odd)

    def test_merge_lab_refuses_what_it_cannot_keep(self):
        from bv import voicelab
        old = "voices:\n  troll-female/old:\n    - 4  # x\n  zandalari-male: []\n"
        with self.assertRaises(ValueError):
            voicelab.merge_lab(old, [("troll-female/old", [], [3])], "t")

    def test_the_switches(self):
        from bv import voicelab
        self.assertEqual(voicelab.parse_args(["E:/lab"]), (Path("E:/lab"), "", True))
        self.assertEqual(voicelab.parse_args(["E:/lab", "--only", "troll", "--no-f5"]), (Path("E:/lab"), "troll", False))
        self.assertIn("--only <голос>", voicelab.parse_args(["E:/lab", "--only"]))                  # no voice after it
        self.assertIn("--only <голос>", voicelab.parse_args(["E:/lab", "--only", "--no-f5"]))       # a switch, not a voice
        self.assertIn("<папка>", voicelab.parse_args([]))
        self.assertIn("<папка>", voicelab.parse_args(["--no-f5"]))

    def test_the_remote_pick_refuses_and_writes_nothing(self):
        from unittest import mock
        from types import SimpleNamespace
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
        import voicelab_remote
        lab = "voices:\n  orc-male:\n    - 1\n"
        env = {"BV_LAB_HOST": "h", "BV_LAB_INSTALL": "E:\\I", "BV_LAB_DIR": "E:\\L"}
        with tempfile.TemporaryDirectory() as d:
            picks = Path(d) / "voice_picks.yaml"
            picks.write_text("voices: {}\n", encoding="utf-8")
            for remote in (lab + "<<auto>>\n<<heard>>\n",                       # no auto.json
                           lab + "<<auto>>{}<<heard>>{}"):                       # auto.json without the voice
                with mock.patch.dict("os.environ", env), mock.patch.object(voicelab_remote, "PICKS", picks), \
                        mock.patch.object(voicelab_remote, "powershell", return_value=SimpleNamespace(stdout=remote)):
                    self.assertEqual(voicelab_remote.main(["--pick"]), 1, remote)
                self.assertEqual(picks.read_text(encoding="utf-8"), "voices: {}\n")

    def test_file_names(self):
        from bv import voicelab
        self.assertEqual(voicelab.file_name(562829, "прощание", "Пока-пока?", ""), "562829 прощание Пока-пока")
        self.assertEqual(voicelab.file_name(1, 'Он сказал: "да/нет".'), "1 Он сказал данет")
        self.assertLessEqual(len(voicelab.file_name("x" * 200)), 90)


class LabRuns(unittest.TestCase):
    """The voice lab's runs with the game, Whisper and the decoder faked: a line's samples carry its file id, its
    length is `seconds[id]`, its transcript `texts[id]`."""

    def setUp(self):
        import contextlib
        from unittest import mock

        import numpy as np
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.dir, ignore_errors=True))
        self.table = {
            "orc-male": {"race": "orc", "sex": "male", "files": [[i, "error", 1] for i in range(1, 13)]},
            "troll-female/old": {"race": "troll", "sex": "female", "files": [[i, "vendor", 1] for i in range(21, 25)]},
        }
        self.texts = {i: f"Это реплика номер {i} для проверки." for i in range(1, 25)}
        self.seconds = {i: 2.0 for i in range(1, 25)}
        self.asked = []
        self.logged = []
        self.picks = self.dir / "voice_picks.yaml"
        test = self

        class Store:
            def __init__(self, *_):
                self.missing, self.borrowed = [], 0

            def read_files(self, wanted, *_):
                return {f: f for f in wanted}

        class Checker:
            def __init__(self, *_):
                pass

            def load(self):
                return True

            def transcribe(self, x, rate):
                test.asked.append(int(x[0]))
                return test.texts[int(x[0])]

            def score(self, x, rate, text):
                return 1.0, text
        self.Checker = Checker
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        for patch in (mock.patch.object(gamevoices, "_stamp", return_value={"install": "x", "product": "wowf"}),
                      mock.patch.object(gamevoices, "voices_for", side_effect=lambda *_: self.table),
                      mock.patch.object(gamevoices, "PICKS", self.picks),
                      mock.patch.object(gamevoices, "other_storages", return_value=[]),
                      mock.patch.object(gamevoices, "_decode",
                                        side_effect=lambda f: np.full(int(self.seconds[f] * 24000), f, dtype="float32")),
                      mock.patch.object(casc, "Storage", Store),
                      mock.patch("bv.whisper_onnx.OnnxChecker", Checker),
                      mock.patch("bv.f5engine.preload")):
            stack.enter_context(patch)

    def lab(self, only=""):
        from bv import voicelab
        self.assertEqual(voicelab.run({}, self.dir, self.dir / "lab", self.logged.append, only=only, f5=False), 0)
        return gamevoices.load_picks(self.dir / "lab" / "voices.yaml")

    def edit(self, voice, ids):
        """voices.yaml with `voice`'s lines `ids` (in that order) the only items, the rest of it commented."""
        path = self.dir / "lab" / "voices.yaml"
        from bv import voicelab
        kept = voicelab.blocks(path.read_text(encoding="utf-8"))
        lines = [line for line in kept[voice].splitlines()[1:]]
        by_id = {int(re.search(r"- (\d+)", line).group(1)): line.lstrip(" #").lstrip() for line in lines}
        kept[voice] = f"  {voice}:\n" + "".join(f"    {by_id[i]}\n" for i in ids) + \
            "".join(f"    # {by_id[i]}\n" for i in by_id if i not in ids)
        path.write_text(voicelab.with_blocks(voicelab.lab_text([], "x").rsplit("voices:", 1)[0], kept), encoding="utf-8")

    def test_the_first_run_takes_the_players_picks(self):
        self.picks.write_text("voices:\n  troll-female/old:\n    - 24\n    - 22\n", encoding="utf-8")
        self.assertEqual(self.lab()["troll-female/old"], [24, 22])
        self.assertEqual(self.lab(only="orc")["troll-female/old"], [24, 22])   # and a voice the lab file lacks

    def test_a_choice_by_ear_is_kept_whatever_comes_of_it(self):
        self.texts[23] = ""                                          # Whisper heard no words in it
        self.lab()
        self.edit("troll-female/old", [22, 23])                      # 2 s of speech: under MIN_SPEECH
        path = self.dir / "lab" / "voices.yaml"
        path.write_text(path.read_text(encoding="utf-8").replace("    - 23  #", "    - 99\n    - 23  #"),
                        encoding="utf-8")                          # and a file that is not this voice's
        self.logged.clear()
        self.assertEqual(self.lab()["troll-female/old"], [22, 99, 23])               # as chosen, in that order
        voice = self.dir / "lab" / "troll-female" / "old"
        self.assertFalse((voice / "sample.wav").exists())
        log = "\n".join(self.logged)
        self.assertIn("99 не взят", log)
        self.assertIn("23 не взят", log)
        self.assertIn("образец не собран", log)

    def test_a_voice_with_every_line_commented_stays_out(self):
        self.lab()
        self.edit("troll-female/old", [])
        self.assertEqual(self.lab()["troll-female/old"], [])
        self.assertFalse((self.dir / "lab" / "troll-female" / "old" / "sample.wav").exists())

    def test_the_order_by_ear(self):
        self.lab()
        self.edit("troll-female/old", [24, 21, 23])
        self.lab()
        names = sorted(p.name for p in (self.dir / "lab" / "troll-female" / "old" / "used").iterdir())
        self.assertEqual([n.split()[1] for n in names], ["24", "21", "23"])

    def test_only_one_voice_keeps_the_others(self):
        self.lab()
        self.edit("orc-male", [5, 6, 7])
        self.lab(only="troll")
        self.assertEqual(self.lab(only="troll")["orc-male"], [5, 6, 7])
        self.assertEqual(self.asked.count(5), 1)                    # heard once, in the first run

    def test_all_shows_every_line_the_bank_would_not_hear(self):
        self.seconds[12] = 8.0                                      # too long for a clip
        self.lab()
        names = [p.name for p in (self.dir / "lab" / "orc-male" / "all").iterdir()]
        self.assertEqual(len(names), 12)                            # the bank stops listening after 8
        self.assertTrue(any(n.startswith("12 ошибка (не годится)") for n in names), names)

    def test_the_lab_file_wins_over_the_players_file(self):
        self.picks.write_text("voices:\n  troll-female/old:\n    - 24\n    - 22\n", encoding="utf-8")
        self.lab()
        self.edit("troll-female/old", [21, 23])
        self.assertEqual(self.lab()["troll-female/old"], [21, 23])

    def test_the_automatic_choice_is_kept_beside(self):
        # auto.json: the bank's choice, in its order - and the lab file has it for an unchanged voice
        picks = self.lab()
        auto = json.loads((self.dir / "lab" / "auto.json").read_text(encoding="utf-8"))
        self.assertEqual(picks, auto)
        self.assertFalse(any("выбрано вручную" in m for m in self.logged))
        self.edit("troll-female/old", [24, 21, 23])
        self.logged.clear()
        self.lab()
        self.assertEqual(json.loads((self.dir / "lab" / "auto.json").read_text(encoding="utf-8")), auto)
        self.assertEqual([m for m in self.logged if "выбрано вручную" in m],
                         [m for m in self.logged if "troll-female/old" in m and "выбрано вручную" in m])
        self.assertTrue(any("выбрано вручную" in m for m in self.logged))

    def test_only_runs_one_voice(self):
        self.lab()
        marker = self.dir / "lab" / "orc-male" / "mine.txt"
        marker.write_text("x", encoding="utf-8")
        self.logged.clear()
        self.lab(only="troll-female/old")
        self.assertIn("голосов: 1", "\n".join(self.logged))
        self.assertTrue(marker.exists() and (self.dir / "lab" / "orc-male" / "sample.wav").exists())

    def test_a_clip_out_of_the_good_length_is_told(self):
        self.lab()
        self.edit("orc-male", [1, 2, 3, 4, 5, 6])                    # 12 s
        self.logged.clear()
        self.lab()
        self.assertTrue(any("orc-male: речи в образце 12.0 с" in m for m in self.logged), self.logged)
        self.edit("orc-male", [1, 2])                                # 4 s: a clip, but short
        self.logged.clear()
        self.lab()
        self.assertTrue(any("orc-male: речи в образце 4.0 с" in m for m in self.logged), self.logged)

    def test_a_text_corrected_in_the_lab_file(self):
        self.lab()
        path = self.dir / "lab" / "voices.yaml"
        lab = path.read_text(encoding="utf-8")
        used = gamevoices.picks_of(lab)["troll-female/old"]
        old = f'- {used[0]}: "{self.texts[used[0]]}"'
        path.write_text(lab.replace(old, f'- {used[0]}: "Исправлено руками."'), encoding="utf-8")
        self.lab()
        sample = (self.dir / "lab" / "troll-female" / "old" / "sample.txt").read_text(encoding="utf-8")
        self.assertTrue(sample.startswith("Исправлено руками."), sample)
        transcripts = json.loads((self.dir / "lab" / "transcripts.json").read_text(encoding="utf-8"))
        self.assertEqual(transcripts[str(used[0])], self.texts[used[0]])          # Whisper's stays as it heard
        # --pick: the voice is the automatic choice, but its text was corrected: it goes to the players
        from bv import voicelab
        auto = json.loads((self.dir / "lab" / "auto.json").read_text(encoding="utf-8"))
        picks = voicelab.to_picks(path.read_text(encoding="utf-8"), "voices: {}\n", auto, "", transcripts)
        self.assertEqual(list(gamevoices.lines_of(picks)), ["troll-female/old"])
        self.assertEqual(gamevoices.lines_of(picks)["troll-female/old"][0], (used[0], "Исправлено руками."))
        # without the correction: nothing differs from the automatic choice, nothing goes
        plain = voicelab.to_picks(lab, "voices: {}\n", auto, "", transcripts)
        self.assertEqual(gamevoices.lines_of(plain), {})

    def test_the_lab_shows_the_players_clips(self):
        # without picks the lab's clip of every voice is the bank's: the bank stops listening once it has enough
        # calm lines and chooses among those (lines 9-12 would fit better: 3 s)
        for i in range(9, 13):
            self.seconds[i] = 3.0
        slots = gamevoices.build({}, self.dir / "voices", lambda *a: None, self.Checker())
        self.lab()
        for slot in slots:
            lab = (self.dir / "lab" / slot.id / "sample.txt").read_text(encoding="utf-8").strip()
            self.assertEqual(lab, slot.text, slot.id)

    def test_an_untouched_voice_follows_its_automatic_choice(self):
        # a game update takes a line away: the lab file still has the old automatic choice - not a choice by ear
        from bv import voicelab
        first = self.lab()["orc-male"]
        auto = json.loads((self.dir / "lab" / "auto.json").read_text(encoding="utf-8"))
        self.assertEqual(gamevoices.lines_of(voicelab.to_picks(
            (self.dir / "lab" / "voices.yaml").read_text(encoding="utf-8"), "", auto, "", {})), {})
        self.table["orc-male"]["files"] = [f for f in self.table["orc-male"]["files"] if f[0] != first[0]]
        self.logged.clear()
        now = self.lab()["orc-male"]
        self.assertNotIn(first[0], now)
        self.assertFalse(any("выбрано вручную" in m or "не взят" in m for m in self.logged), self.logged)
        auto = json.loads((self.dir / "lab" / "auto.json").read_text(encoding="utf-8"))
        self.assertEqual(now, auto["orc-male"])
        lab = (self.dir / "lab" / "voices.yaml").read_text(encoding="utf-8")
        self.assertEqual(gamevoices.lines_of(voicelab.to_picks(lab, "", auto, "", {})), {})

    def test_pick_needs_every_voice_s_automatic_choice(self):
        from bv import voicelab
        lab = "voices:\n  a:\n    - 1\n  b:\n    - 3\n  c: []\n"
        for auto in ({"a": [1]}, {}):
            with self.assertRaises(ValueError) as stop:
                voicelab.to_picks(lab, "", auto, "")
            self.assertIn("без --only", str(stop.exception))

    def test_a_lab_file_it_cannot_write_back_stops_the_run_first(self):
        from bv import voicelab
        self.lab()
        path = self.dir / "lab" / "voices.yaml"
        odd = path.read_text(encoding="utf-8") + "  zandalari-male: [5, 6]\n"      # glued to the last block
        path.write_text(odd, encoding="utf-8")
        self.logged.clear()
        self.assertEqual(voicelab.run({}, self.dir, self.dir / "lab", self.logged.append, f5=False), 1)
        self.assertEqual(path.read_text(encoding="utf-8"), odd)                      # as it was
        self.assertFalse(any(m.startswith("голосов:") for m in self.logged), self.logged)   # before any work
        self.assertTrue(any("не получится переписать голоса" in m and "zandalari-male" in m for m in self.logged),
                        self.logged)

    def test_a_clip_open_in_a_player(self):
        from unittest import mock
        from bv import voicelab
        self.lab()
        unlink = Path.unlink

        def locked(path, *a, **k):
            if path.name == "sample.wav":
                raise PermissionError("in use")
            return unlink(path, *a, **k)
        with mock.patch.object(Path, "unlink", locked):
            self.assertEqual(voicelab.run({}, self.dir, self.dir / "lab", self.logged.append, f5=False), 1)
        self.assertIn("открыт в другой программе", self.logged[-1])
        # soundfile's own error (LibsndfileError is a RuntimeError): the same kind of message, not its traceback
        import soundfile
        self.logged.clear()
        with mock.patch.object(soundfile, "write", side_effect=soundfile.LibsndfileError(2, "Error opening: ")):
            self.assertEqual(voicelab.run({}, self.dir, self.dir / "lab", self.logged.append, f5=False), 1)
        self.assertIn("закрой его файлы в других программах", self.logged[-1])
        # a bug of the lab's own is no file open in a player: as it is
        with mock.patch.object(voicelab, "_write_voice", side_effect=KeyError(5)), self.assertRaises(KeyError):
            voicelab.run({}, self.dir, self.dir / "lab", self.logged.append, f5=False)

    def test_a_run_stopped_midway_keeps_auto_json_with_its_lab_file(self):
        # auto.json goes with the voices.yaml it was made with: else the old lists would pass for choices by ear
        from unittest import mock
        from bv import voicelab
        first = self.lab()["orc-male"]
        self.table["orc-male"]["files"] = [f for f in self.table["orc-male"]["files"] if f[0] != first[0]]
        auto = (self.dir / "lab" / "auto.json").read_text(encoding="utf-8")
        self.table["orc-male"]["files"].append([13, "error", 1])           # a new line, heard before the stop
        self.texts[13], self.seconds[13] = "Новая реплика для проверки.", 2.0
        with mock.patch.object(voicelab, "_write_voice", side_effect=[None, OSError("System error")]):
            self.assertEqual(voicelab.run({}, self.dir, self.dir / "lab", self.logged.append, f5=False), 1)
        self.assertEqual((self.dir / "lab" / "auto.json").read_text(encoding="utf-8"), auto)
        # what Whisper heard is kept whatever comes: transcripts.json is a cache
        transcripts = json.loads((self.dir / "lab" / "transcripts.json").read_text(encoding="utf-8"))
        self.assertEqual(transcripts["13"], self.texts[13])
        self.logged.clear()
        self.assertNotIn(first[0], self.lab()["orc-male"])
        self.assertFalse(any("выбрано вручную" in m or "не взят" in m for m in self.logged), self.logged)

    def test_the_refusal_at_the_end_writes_neither_file(self):
        from unittest import mock
        from bv import voicelab
        self.lab()
        files = {n: (self.dir / "lab" / n).read_text(encoding="utf-8") for n in ("voices.yaml", "auto.json")}
        self.table["orc-male"]["files"] = self.table["orc-male"]["files"][1:]
        with mock.patch.object(voicelab, "merge_lab", side_effect=ValueError("не получилось переписать голоса x")):
            self.assertEqual(voicelab.run({}, self.dir, self.dir / "lab", self.logged.append, f5=False), 1)
        self.assertEqual(self.logged[-1], "не получилось переписать голоса x")
        for name, text in files.items():
            self.assertEqual((self.dir / "lab" / name).read_text(encoding="utf-8"), text, name)

    def test_a_corrected_text_is_told_and_a_twice_listed_line_keeps_it(self):
        self.lab()
        path = self.dir / "lab" / "voices.yaml"
        lab = path.read_text(encoding="utf-8")
        used = gamevoices.picks_of(lab)["troll-female/old"]
        line = f'    - {used[0]}: "{self.texts[used[0]]}"'
        row = next(r for r in lab.splitlines() if r.startswith(line))
        # one copy corrected, the other as Whisper heard it: the corrected one, whichever comes first
        for both in (f'    - {used[0]}: "Исправлено руками."\n' + row, row + f'\n    - {used[0]}: "Исправлено руками."'):
            path.write_text(lab.replace(row, both), encoding="utf-8")
            self.logged.clear()
            self.lab()
            sample = (self.dir / "lab" / "troll-female" / "old" / "sample.txt").read_text(encoding="utf-8")
            self.assertTrue(sample.startswith("Исправлено руками. Исправлено руками."), sample)
        self.assertIn(f"troll-female/old: текст фразы {used[0]} не как у Whisper — оставлен как выбор на слух",
                      self.logged)

    def test_a_voice_commented_out_whole_is_kept_as_a_comment(self):
        self.lab()
        path = self.dir / "lab" / "voices.yaml"
        lab = path.read_text(encoding="utf-8")
        from bv import voicelab
        block = voicelab.blocks(lab)["orc-male"]
        toggled = "".join("  # " + r[2:] + "\n" for r in block.splitlines())    # an editor's «comment out»
        path.write_text(lab.replace(block, toggled), encoding="utf-8")
        self.assertIn("orc-male", self.lab())                  # made again, as a voice the file lacks
        self.assertIn(toggled, path.read_text(encoding="utf-8"))

    def test_the_only_run_keeps_the_full_run_s_pace(self):
        from unittest import mock
        from bv import voicelab
        paces = iter([0.1, 0.2])
        with mock.patch.object(voicelab, "speak", lambda *a, **k: next(paces)):
            voicelab.run({}, self.dir, self.dir / "lab", self.logged.append)
            voicelab.run({}, self.dir, self.dir / "lab", self.logged.append, only="troll")
        self.assertEqual(json.loads((self.dir / "lab" / "paces.json").read_text(encoding="utf-8")), {"target": 0.1})

    def test_the_game_s_pace_for_only(self):
        # a full run keeps its target pace (paces.json); --only speaks with it, not with the one voice's own
        from unittest import mock
        from bv import voicelab
        targets = []

        def speak(config, home, out, clips, text, log, target=None):
            targets.append(target)
            return 0.123
        with mock.patch.object(voicelab, "speak", speak):
            voicelab.run({}, self.dir, self.dir / "lab", self.logged.append)
            voicelab.run({}, self.dir, self.dir / "lab", self.logged.append, only="troll")
        self.assertEqual(targets, [None, 0.123])
        self.assertEqual(json.loads((self.dir / "lab" / "paces.json").read_text(encoding="utf-8")), {"target": 0.123})

    def test_the_bank_never_asks_whisper_of_a_wrong_length(self):
        self.seconds[1] = 0.5
        self.seconds[2] = 8.0
        gamevoices.build({}, self.dir / "voices", lambda *a: None, self.Checker())
        self.assertNotIn(1, self.asked)
        self.assertNotIn(2, self.asked)


class Listening(unittest.TestCase):
    """listen()'s older rules: a numbered line that is no calm statement goes last, and the bank stops once it has
    heard the calmest kind with room to spare - that kind only, one and a half times the clip's upper length."""

    def lines(self, files, texts, seconds):
        from unittest import mock

        import numpy as np
        asked = []

        class Checker:
            def transcribe(self, x, rate):
                asked.append(int(x[0]))
                return texts[int(x[0])]
        with mock.patch.object(gamevoices, "_decode",
                               side_effect=lambda f: np.full(int(seconds[f] * 24000), f, dtype="float32")):
            heard, _ = gamevoices.listen(files, {f[0]: f[0] for f in files}, Checker())
        return heard, asked

    def test_a_numbered_cry_goes_last(self):
        files = [[1, "line", 2], [2, "line", 2]]
        texts = {1: "За Орду, вперёд!", 2: "Мне это не по силам сейчас."}
        heard, _ = self.lines(files, texts, {1: 2.0, 2: 2.0})
        priority = {h["fdid"]: h["priority"] for h in heard}
        self.assertEqual(priority, {1: 3, 2: 2})                  # «!»: a cry, a joke - after the calm ones
        self.assertEqual(gamevoices.choose(heard)[0]["fdid"], 2)

    def test_it_stops_on_enough_of_the_calmest_kind(self):
        # 2 s lines: the calmest (1) counts, the others (2) do not; 1.5 x 9.5 s = 14.25 s: the eighth calm line
        files = [[i, "error", 1] for i in range(1, 13)] + [[i, "hello", 2] for i in range(20, 30)]
        texts = {i: "Мне это сейчас не по силам." for i in list(range(1, 13)) + list(range(20, 30))}
        seconds = {i: 2.0 for i in texts}
        _, asked = self.lines(files, texts, seconds)
        self.assertEqual(asked, list(range(1, 9)))
        # the calm kind short: the emotes are heard too, all of them - they do not count toward the stop
        files = [[i, "error", 1] for i in range(1, 4)] + [[i, "hello", 2] for i in range(20, 30)]
        _, asked = self.lines(files, texts, seconds)
        self.assertEqual(asked, [1, 2, 3] + list(range(20, 30)))


class Progress(unittest.TestCase):
    def test_progress_lines_and_the_end(self):
        # every PROGRESS_EVERY seconds "собираю голоса рас: N из M", then how many and how long
        from unittest import mock
        table = {f"v{i}": {"race": "orc", "sex": "male", "files": [(i, "line", 1)]} for i in range(5)}

        class Store:
            def __init__(self, *_):
                pass

            def read_files(self, wanted, *_):
                return {f: b"" for f in wanted}

        ticks = iter(range(0, 1000, 6))                    # each look at the clock: 6 s later
        logged = []
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(gamevoices, "_stamp", return_value={"install": d, "product": "wowf"}), \
                mock.patch.object(gamevoices, "load", return_value=None), \
                mock.patch.object(gamevoices, "voices_for", return_value=table), \
                mock.patch.object(gamevoices, "other_storages", return_value=[]), \
                mock.patch.object(gamevoices, "_decode", side_effect=ValueError), \
                mock.patch.object(casc, "Storage", Store):
            slots = gamevoices.build({}, Path(d) / "voices", logged.append, checker=object(), clock=lambda: next(ticks))
        self.assertEqual(slots, [])
        self.assertEqual(logged[0], "собираю голоса рас из игры — несколько минут ...")
        progress = [m for m in logged if m.startswith("собираю голоса рас: ")]
        self.assertTrue(progress and all(m.endswith(" из 5") for m in progress), logged)
        self.assertLess(len(progress), 5)                  # not a line per voice
        self.assertTrue(any(m.startswith("голоса рас собраны: 0 из 5 за ") for m in logged), logged)
        from bv.logs import level_of
        self.assertEqual({level_of(m) for m in progress}, {"INFO"})
        self.assertEqual(level_of("голоса рас собраны: 0 из 5 за 1 мин"), "INFO")

    def test_took(self):
        self.assertEqual(gamevoices.took(40), "40 с")
        self.assertEqual(gamevoices.took(200), "3 мин")


class Table(unittest.TestCase):
    def test_every_race_and_sex_has_voices(self):
        table = json.loads(gamevoices.TABLE.read_text(encoding="utf-8"))["voices"]
        for race in ("human", "orc", "dwarf", "nightelf", "scourge", "tauren", "gnome", "troll"):
            for sex in ("male", "female"):
                ids = [v for v in table if v.split("/")[0] == f"{race}-{sex}"]
                self.assertGreaterEqual(len(ids), 4, f"{race}-{sex}: {ids}")          # the character + 3 NPC types
                self.assertTrue(any(f[2] == 1 for f in table[f"{race}-{sex}"]["files"]))

    def test_skyborne(self):
        # Forever's own race: the character's voice only, calm speech first
        table = json.loads(gamevoices.TABLE.read_text(encoding="utf-8"))["voices"]
        for sex in ("male", "female"):
            files = table[f"skyborne-{sex}"]["files"]
            self.assertGreaterEqual(sum(1 for f in files if f[2] == 1), 20)
            self.assertGreaterEqual(sum(1 for f in files if f[2] == 2), 10)

    def test_retail_races(self):
        # the races retail added: each its own voice per sex, read from the files retail names four ways
        table = json.loads(gamevoices.TABLE.read_text(encoding="utf-8"))["voices"]
        races = ("bloodelf", "draenei", "goblin", "worgen", "pandaren", "dracthyr", "voidelf", "nightborne",
                 "highmountaintauren", "lightforgeddraenei", "darkirondwarf", "zandalaritroll", "magharorc",
                 "kultiran", "mechagnome", "vulpera", "earthendwarf", "haranir")
        for race in races:
            for sex in ("male", "female"):
                self.assertGreaterEqual(len(table[f"{race}-{sex}"]["files"]), 50, f"{race}-{sex}")
        self.assertIn("worgen-male/human", table)                     # a worgen in human form: the Gilnean voice
        tags = {f[1] for f in table["goblin-female"]["files"]}
        self.assertIn("error", tags)
        self.assertNotIn("attack", tags)                              # battle cries left out

    def test_forever_only_its_races(self):
        forever = gamevoices.voices_for({"game": "forever"})
        retail = gamevoices.voices_for({"game": "retail"})
        self.assertEqual({e["race"] for e in forever.values()}, gamevoices.FOREVER_RACES)
        self.assertIn("goblin-male", retail)
        self.assertNotIn("goblin-male", forever)
        self.assertNotIn("skyborne-male", retail)                       # Forever's own race: not in retail

    def test_classify_retail(self):
        sys.path.insert(0, str(gamevoices.TABLE.parents[2] / "tools"))
        from game_voices import classify
        c = "sound/character/"
        self.assertEqual(classify(c + "bloodelf/bloodelffemale_err_nomana01.ogg"), ("bloodelf-female", "error", 1))
        self.assertEqual(classify(c + "draenei/draeneimalehello02.ogg"), ("draenei-male", "hello", 2))
        self.assertIsNone(classify(c + "draenei/draeneimalecharge02.ogg"))
        self.assertEqual(classify(c + "pcgilneanmale/vo_pcgilneanmale_errlootdidntkill01.ogg"),
                         ("worgen-male/human", "error", 1))
        self.assertIsNone(classify(c + "pcworgenmale/vo_pcworgenmale_main_charge01.ogg"))
        self.assertEqual(classify(c + "dracthyr_visage_male/vo_dracthyr_visage_male_nomana_4737525.ogg"),
                         ("dracthyr-male", "error", 1))
        self.assertIsNone(classify(c + "dracthyr_visage_male/vo_dracthyr_visage_male_applaud_4737525.ogg"))
        self.assertEqual(classify(c + "pc_-_void_elf_male/vo_735_pc_-_void_elf_male_01_m.ogg"),
                         ("voidelf-male", "line", 2))
        self.assertIsNone(classify(c + "pc_-_void_elf_male/vo_735_pc_-_void_elf_male_wound01.ogg"))
        self.assertEqual(classify(c + "pc_haranir_female/vo_120_pc_haranir_female_01_f.ogg"),
                         ("haranir-female", "line", 2))


if __name__ == "__main__":
    unittest.main()
