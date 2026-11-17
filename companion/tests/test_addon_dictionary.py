"""The addon's dictionary and the companion's agree: what the dictionary window shows (D.Text) is what the
companion applies (dictionary.merged of the default and the player's layer), and the layer sent over the
strip in parts (ns.SendDictionary) arrives whole (Dictionary.receive). The addon's side runs in LuaJIT."""
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "companion"))

from bv.dictionary import Dictionary, key_of, merged  # noqa: E402
from bv.protocol import crc16, parse  # noqa: E402

ADDON = ROOT / "addon" / "BarrensVoice"
DUMP = Path(__file__).with_name("dictionary_dump.lua")
LUAJIT = shutil.which("luajit")


def addon(case: str) -> tuple[str, str, str, list[bytes]]:
    """The addon's default, its D.Text(), the layer its saved variables keep and the "dict" frames, for a case of
    dictionary_dump.lua."""
    out = subprocess.run([LUAJIT, str(DUMP), case], cwd=ADDON, capture_output=True, check=True).stdout
    default, text, layer, *frames = out.split(b"\0")
    return default.decode(), text.decode(), layer.decode(), frames


def entries(text: str) -> list[str]:
    return sorted(line.strip() for line in text.splitlines() if key_of(line))


@unittest.skipUnless(LUAJIT, "luajit not installed")
class AddonAndCompanion(unittest.TestCase):
    def test_the_window_shows_what_the_companion_applies(self):
        for case in ("none", "edited", "many"):
            with self.subTest(case):
                default, text, layer, _ = addon(case)
                user = "" if layer == "-" else layer
                self.assertEqual(entries(text), sorted(merged(default, user)))
                if case == "none":
                    self.assertEqual(layer, "-")
                if case == "edited":
                    self.assertIn("абв=где", user)
                    self.assertTrue(any(line.startswith("!") for line in user.splitlines()), user)

    def test_the_layer_arrives_whole(self):
        for case in ("none", "edited", "many", "long"):
            with self.subTest(case):
                _, _, layer, frames = addon(case)
                if case == "many":
                    self.assertGreater(len(frames), 3)
                logged = []
                d = Dictionary({}, logged.append)
                for frame in frames:
                    line = parse(frame)
                    self.assertEqual(line.kind, "dict")
                    d.receive(line.options, line.text)
                self.assertEqual(d.from_addon, parse(frames[0]).options["id"])
                self.assertEqual(d.user, "" if layer == "-" else layer)
                self.assertTrue(logged, "rebuilt once complete")

    def test_a_long_line_is_left_out_of_the_frames_and_the_saved_variables_alike(self):
        """A line longer than a part is not sent over the strip; the saved variables, read when the frames have
        not come, must not carry it either, or the rule would work in some sessions and not in others."""
        _, text, layer, frames = addon("long")
        self.assertTrue(any(len(line.encode()) > 480 for line in text.splitlines()), "the window keeps it")
        self.assertEqual(layer, "абв=где")
        d = Dictionary({}, lambda _: None)
        for frame in frames:
            line = parse(frame)
            d.receive(line.options, line.text)
        self.assertEqual(d.user, layer)
        self.assertEqual(d.from_addon, f"{crc16(layer.encode()):04x}", "the id is the sent layer's")


if __name__ == "__main__":
    unittest.main()
