"""The voice bank from the game client: reading the storage, choosing lines, the cache."""
import json
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
