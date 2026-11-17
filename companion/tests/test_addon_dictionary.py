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
from bv.protocol import parse  # noqa: E402

ADDON = ROOT / "addon" / "BarrensVoice"
DUMP = Path(__file__).with_name("dictionary_dump.lua")
LUAJIT = shutil.which("luajit")


def addon(case: str) -> tuple[str, str, str, list[bytes]]:
    """The addon's default, its D.Text(), D.UserLayer() and the "dict" frames, for a case of dictionary_dump.lua."""
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
        for case in ("none", "edited", "many"):
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


if __name__ == "__main__":
    unittest.main()
