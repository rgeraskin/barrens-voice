"""The voice bank from the game client: reading the storage, choosing lines, the cache."""
import json
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wcv import casc, gamevoices  # noqa: E402


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

    def test_root_keeps_only_wanted(self):
        ru, en = casc.LOCALES["ruRU"], casc.LOCALES["enUS"]
        raw = root_v2([(en, [(10, b"E" * 16), (12, b"F" * 16)]), (ru, [(10, b"R" * 16)])])
        self.assertEqual(casc.parse_root(raw, {10}), {10: [(en, b"E" * 16), (ru, b"R" * 16)]})
        self.assertEqual(casc.parse_root(raw, {12, 99}), {12: [(en, b"F" * 16)]})

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
            slot = {"id": "orc-male", "base": "orc-male", "race": "orc", "sex": "male", "shift": 0.0,
                    "path": "x.wav", "text": "Текст.", "speech": 2.0}
            out.mkdir()
            (out / "bank.json").write_text(json.dumps({"stamp": stamp, "slots": [slot]}), encoding="utf-8")
            self.assertFalse(gamevoices.stale(config, out))
            slots = gamevoices.build(config, out, print, checker=None)                 # no Whisper needed
            self.assertEqual([s.id for s in slots], ["orc-male"])
            info.write_text(head + "eu|1|" + "b" * 32 + "|1.15.9|wowf\n", encoding="utf-8")
            self.assertTrue(gamevoices.stale(config, out))                             # the game was updated
            with self.assertRaises(RuntimeError):
                gamevoices.build(config, out, print, checker=None)                     # and Whisper is needed


class Table(unittest.TestCase):
    def test_every_race_and_sex_has_voices(self):
        table = json.loads(gamevoices.TABLE.read_text(encoding="utf-8"))["voices"]
        for race in ("human", "orc", "dwarf", "nightelf", "scourge", "tauren", "gnome", "troll"):
            for sex in ("male", "female"):
                ids = [v for v in table if v.split("/")[0] == f"{race}-{sex}"]
                self.assertGreaterEqual(len(ids), 4, f"{race}-{sex}: {ids}")          # the character + 3 NPC types
                self.assertTrue(any(f[2] == 1 for f in table[f"{race}-{sex}"]["files"]))


if __name__ == "__main__":
    unittest.main()
