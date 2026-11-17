"""The companion's own plumbing that runs without Windows: config.json, the files it writes into the addon."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bv import __main__ as companion  # noqa: E402


class LoadConfig(unittest.TestCase):
    def load(self, text: str | None):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            if text is not None:
                path.write_text(text, encoding="utf-8")
            logged = []
            config = companion.load_config(path, logged.append)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(sorted(p.name for p in Path(d).iterdir()), ["config.json"])   # no .tmp left
            return config, saved, logged

    def test_made_then_completed(self):
        config, saved, _ = self.load(None)
        self.assertEqual(config, companion.DEFAULT_CONFIG)
        self.assertEqual(saved, companion.DEFAULT_CONFIG)
        config, saved, _ = self.load('{"players": {"Тралл": "orc-male"}}')
        self.assertEqual(config["players"], {"Тралл": "orc-male"})
        self.assertEqual(saved["players"], {"Тралл": "orc-male"})
        self.assertEqual(saved["max_queue"], companion.DEFAULT_CONFIG["max_queue"])   # new settings written in

    def test_not_json_is_said_in_words(self):
        # it died with a traceback before the launcher could be told anything
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            for text, words in (('{\n  "players": {},\n}\n', "строке 2"), ("[1, 2]", "фигурных скобках"),
                                ('{"wow_dir": "D:\\Games"}', "строке 1")):
                path.write_text(text, encoding="utf-8")
                with self.assertRaises(companion.ConfigError) as told:
                    companion.load_config(path, lambda *a: None)
                self.assertIn(words, str(told.exception))
                self.assertTrue(str(told.exception).startswith("config.json не читается"))
                self.assertEqual(path.read_text(encoding="utf-8"), text)     # the player's file left alone
            path.write_bytes(b'{"x": "\xff"}')
            with self.assertRaises(companion.ConfigError):
                companion.load_config(path, lambda *a: None)

    def test_numbers(self):
        # "max_queue": 0 raised IndexError in queue_line, "poll_interval": 0 ZeroDivisionError, "8" a TypeError
        config, _, logged = self.load('{"max_queue": 0, "poll_interval": 0, "volume": "80", "rate": "fast", '
                                      '"f5_margin": 1}')
        self.assertEqual(config["max_queue"], 1)
        self.assertEqual(config["poll_interval"], 0.01)
        self.assertEqual(config["volume"], 80)
        self.assertEqual(config["rate"], companion.DEFAULT_CONFIG["rate"])
        self.assertEqual(config["f5_margin"], 1)
        self.assertEqual(len(logged), 3, logged)
        from bv.logs import level_of
        self.assertEqual({level_of(m) for m in logged}, {"WARN"})


class AddonFiles(unittest.TestCase):
    """VoiceList.lua, CompanionStatus.lua and DictionaryOnline.lua: written whole or not at all."""

    def test_write_if_changed(self):
        from bv.paths import write_if_changed
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "VoiceList.lua"
            self.assertTrue(write_if_changed(path, "a = 1\n"))
            self.assertFalse(write_if_changed(path, "a = 1\n"))           # the same: not written again
            self.assertTrue(write_if_changed(path, "a = 2\n"))
            self.assertEqual(path.read_text(encoding="utf-8"), "a = 2\n")
            self.assertEqual([p.name for p in Path(d).iterdir()], ["VoiceList.lua"])
            with self.assertRaises(OSError):
                write_if_changed(Path(d) / "gone" / "VoiceList.lua", "x")

    def test_a_voice_list_that_cannot_be_written_does_not_stop_the_companion(self):
        # voicelist.write ran bare at the start: a locked VoiceList.lua ended the companion
        from unittest import mock

        from bv import voicelist
        logged = []
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(voicelist, "find_addon", return_value=Path(d)), \
                mock.patch("bv.paths.write_if_changed", side_effect=PermissionError("locked")):
            voicelist.write({}, [], lambda v: False, logged.append)
        self.assertEqual(logged, ["не удалось записать список голосов Windows в аддон: locked"])
        with tempfile.TemporaryDirectory() as d, mock.patch.object(voicelist, "find_addon", return_value=Path(d)):
            voicelist.write({}, [], lambda v: False, logged.append)
            self.assertTrue((Path(d) / "VoiceList.lua").is_file())


if __name__ == "__main__":
    unittest.main()
