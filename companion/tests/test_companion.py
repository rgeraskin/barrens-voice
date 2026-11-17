"""The companion's own plumbing that runs without Windows: config.json, service frames and chat lines,
the files it writes into the addon."""
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

    def test_bom_is_read(self):
        # Notepad's «UTF-8 with BOM»: the launcher read it, the companion stopped with CONFIG_ERROR
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            path.write_text('{"players": {"Тралл": "orc-male"}}', encoding="utf-8-sig")
            self.assertEqual(companion.load_config(path, lambda *a: None)["players"], {"Тралл": "orc-male"})

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


class LiveSettings(unittest.TestCase):
    """`LiveConfig`: the launcher's «Закрываться вместе с игрой» taken while the companion runs, whatever
    the file is like at the moment it is looked at."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "config.json"
        self.tick = 0

    def tearDown(self):
        self.dir.cleanup()

    def write(self, text: str, encoding: str = "utf-8"):
        import os
        self.path.write_text(text, encoding=encoding)
        self.tick += 10
        os.utime(self.path, (self.tick, self.tick))        # a new stamp, whatever the clock's grain

    def loaded(self):
        self.write(json.dumps(dict(companion.DEFAULT_CONFIG, exit_with_wow=True)))
        config, stamp = companion.load_config_stamped(self.path, lambda *a: None)
        self.assertIsNotNone(stamp)                         # nothing new written: the file's own stamp
        return config, stamp

    def test_a_read_that_fails_is_tried_again(self):
        # the stamp was kept before the read: one sharing violation lost the change until the next one
        from unittest import mock
        config, stamp = self.loaded()
        live = companion.LiveConfig(config, self.path, stamp)
        self.write(json.dumps({"exit_with_wow": False}))
        with mock.patch.object(Path, "read_text", side_effect=PermissionError("sharing violation")):
            live.refresh()
        self.assertTrue(config["exit_with_wow"])
        live.refresh()
        self.assertFalse(config["exit_with_wow"])

    def test_a_file_that_is_no_settings_is_left_alone(self):
        # null or 5 raised TypeError in the main loop: the running companion died
        config, stamp = self.loaded()
        live = companion.LiveConfig(config, self.path, stamp)
        for text in ("null", "5", "true", '"exit_with_wow"', "[]", '{"exit_with_wow": fal', '{"exit_with_wow": "false"}'):
            self.write(text)
            live.refresh()
            self.assertTrue(config["exit_with_wow"], text)
        self.write('{"exit_with_wow": false}')               # saved whole at last: taken
        live.refresh()
        self.assertFalse(config["exit_with_wow"])

    def test_a_change_before_the_first_look(self):
        # the stamp was first taken after the voice bank and the game's launch: a box unchecked meanwhile
        # was never seen
        config, stamp = self.loaded()
        self.write(json.dumps(dict(companion.DEFAULT_CONFIG, exit_with_wow=False)))
        live = companion.LiveConfig(config, self.path, stamp)
        live.refresh()
        self.assertFalse(config["exit_with_wow"])

    def test_a_file_the_companion_wrote_is_read_at_the_first_look(self):
        # new settings written in: the stamp is that of our own write, which may hide the launcher's
        self.write('{"exit_with_wow": false}')
        config, stamp = companion.load_config_stamped(self.path, lambda *a: None)
        self.assertIsNone(stamp)
        config["exit_with_wow"] = True
        companion.LiveConfig(config, self.path, stamp).refresh()
        self.assertFalse(config["exit_with_wow"])

    def test_bom(self):
        # Notepad's «UTF-8 with BOM»
        config, stamp = self.loaded()
        live = companion.LiveConfig(config, self.path, stamp)
        self.write('{"exit_with_wow": false}', encoding="utf-8-sig")
        live.refresh()
        self.assertFalse(config["exit_with_wow"])


class ServiceFrames(unittest.TestCase):
    """Frames that are not chat: state counts even in the frame that was up at the start, a command
    or a click only in a new one - and none of them is «строки типа … не озвучиваю»."""

    def run_frame(self, kind, first, text="-", options=None):
        from unittest import mock

        from bv.protocol import Line
        calls, logged = [], []

        class Fake:
            place = None

            def __getattr__(self, name):
                def call(*args):
                    calls.append(name)
                    return True
                return call
        fake = Fake()
        line = Line(kind, "", "", "", "", "", text, options=options or {})
        with mock.patch.object(companion, "log", logged.append), \
                mock.patch("bv.links.open_link", lambda *a: calls.append("open_link")), \
                mock.patch("bv.links.copy_link", lambda *a: calls.append("copy_link")):
            self.assertIn(kind, companion.SERVICE_KINDS)
            companion.service(line, first, fake, fake, fake, fake)
        return calls, logged

    def test_commands_only_when_new(self):
        # reset or diag as the very first frame fell through to «строки типа «reset» не озвучиваю»
        for kind, call in (("stop", "stop"), ("reset", "reset_assignments"), ("open", "open_link"),
                           ("copy", "copy_link"), ("diag", None)):
            calls, logged = self.run_frame(kind, first=True)
            self.assertEqual((calls, logged), ([], []), kind)
            calls, logged = self.run_frame(kind, first=False, text="проверка")
            if call:
                self.assertEqual(calls, [call], kind)
            else:
                self.assertEqual(logged, ["[диагностика аддона] проверка"])

    def test_state_even_when_first(self):
        for kind, call in (("dict", "receive"), ("pause", "pause"), ("resume", "resume")):
            for first in (True, False):
                self.assertEqual(self.run_frame(kind, first)[0], [call], kind)
        calls, logged = self.run_frame("control", True, options={"strip": "0,0,1920,16,1920,1080"})
        self.assertEqual(calls, ["set_place"])
        self.assertTrue(logged[0].startswith("полоска: верх"), logged)


class ChatLines(unittest.TestCase):
    """`Lines`: what a new frame's line does - settings for the engines, service frames, chat lines
    spoken with the speaker's name or without it, repeats and unknown kinds left unread."""

    class Engines:
        def __init__(self, test):
            self.test, self.followed, self.quiet, self.stopped = test, [], 0.0, 0

        def follow(self, line):
            self.followed.append(line.kind)

        def quiet_for(self):
            return self.quiet

        def for_line(self, line):
            return self.test.speaker

        def stop(self):
            self.stopped += 1

    class Speaker:
        def __init__(self):
            self.said = []

        def describe(self, line):
            return "orc-male"

        def say(self, line):
            self.said.append(line)

    class Seen:
        def __init__(self):
            self.ids = set()

        def seen(self, line_id):
            if line_id and line_id in self.ids:
                return True
            self.ids.add(line_id)
            return False

    def setUp(self):
        from unittest import mock
        self.logged, self.disabled, self.texts = [], [], []
        self.engines, self.speaker, self.seen = self.Engines(self), self.Speaker(), self.Seen()
        sapi = mock.Mock()
        sapi.set_disabled.side_effect = self.disabled.append
        self.config = {"same_speaker_gap": 5.0, "log_details": True}
        self.lines = companion.Lines(self.config, self.logged.append, self.engines, sapi, None, "dictionary",
                                     None, "inflector", "restore_yo", self.seen)

        def speech_text(text, dictionary, inflector, declension, restore_yo):
            self.texts.append((text, dictionary, inflector, declension, restore_yo))
            return text.strip().upper()
        for patch in (mock.patch.object(companion, "speech_text", speech_text),
                      mock.patch.object(companion, "log", self.logged.append)):     # service()'s own
            patch.start()
            self.addCleanup(patch.stop)

    def line(self, text, kind="party", sender="Тралл", channel="", first=False, **options):
        from bv.protocol import Line
        raw = options.pop("raw", "")
        decl = options.get("decl", "1") != "0"
        line = Line(kind, sender, "Orc", "2", "SHAMAN", channel, text, off=options.get("off"), declension=decl,
                    options=options, raw=raw)
        self.lines.handle(line, first)
        return line

    def spoken(self):
        return [line.text for line in self.speaker.said]

    def test_a_chat_line(self):
        self.line("Тралл:\x04 привет", raw="привет!", decl="0")
        self.assertEqual(self.spoken(), ["Тралл: ПРИВЕТ"])               # the rules on the line, not the name
        self.assertEqual(self.texts, [(" привет", "dictionary", "inflector", False, "restore_yo")])
        self.assertEqual(self.logged, ["[группа] Тралл (Orc, м) → orc-male: Тралл: ПРИВЕТ",
                                       "    исходно:   привет!"])
        self.logged.clear()
        self.line("Тралл:\x04 ещё", kind="channels", channel="Торговля", sender="Джайна")
        self.assertEqual(self.logged, ["[канал Торговля] Джайна (Orc, м) → orc-male: Тралл: ЕЩЁ"])
        self.logged.clear()
        self.line("ОК", raw="ОК")                                        # the same as spoken: no second line
        self.assertEqual(len(self.logged), 1)
        self.config["log_details"] = False
        self.line("Тралл:\x04 и ещё", raw="и ещё!")
        self.assertNotIn("    исходно:   и ещё!", self.logged)

    def test_the_same_character_goes_on_without_the_name(self):
        self.line("Тралл:\x04 раз")
        self.line("Тралл:\x04 два")                                       # within same_speaker_gap
        self.engines.quiet = 5.1
        self.line("Тралл:\x04 три")                                       # heard a while ago: named again
        self.engines.quiet = 0
        self.line("Джайна:\x04 четыре", sender="Джайна")                  # another character
        self.line("Джайна:\x04 пять", sender="Джайна", kind="say")        # another chat
        self.line("Джайна\x05 смеётся", sender="Джайна", kind="say")      # an emote's name is kept
        self.line("Джайна\x05 машет", sender="Джайна", kind="say")
        self.assertEqual(self.spoken(), ["Тралл: РАЗ", "ДВА", "Тралл: ТРИ", "Джайна: ЧЕТЫРЕ", "Джайна: ПЯТЬ",
                                         "Джайна СМЕЁТСЯ", "Джайна МАШЕТ"])

    def test_not_spoken(self):
        self.line("Тралл:\x04 было", first=True)                        # up before the start: not news
        self.line("", kind="party")                                       # nothing to say
        self.line("Тралл:\x04 раз", id="17")
        self.line("Тралл:\x04 раз", id="17")                              # sent again
        self.line("что-то", kind="future")
        self.line("что-то ещё", kind="future")
        self.assertEqual(self.spoken(), ["Тралл: РАЗ"])
        self.assertEqual(self.logged[1:], ["строка 17 уже прочитана — пропускаю повтор",
                                           "строки типа «future» не озвучиваю (аддон новее программы?)"])
        self.assertEqual(self.engines.followed, ["party", "party", "party", "party", "future", "future"])
        self.lines.handle(None, False)                                    # a frame that is no line
        self.assertEqual(len(self.engines.followed), 6)

    def test_settings_and_service_frames(self):
        self.line("", kind="control", off="Irina|Pavel|")
        self.line("", kind="control", off="")
        self.line("", kind="stop", first=True)                            # a command only in a new frame
        self.line("", kind="stop")
        self.assertEqual(self.disabled, [{"Irina", "Pavel"}, set()])
        self.assertEqual((self.engines.followed, self.engines.stopped), (["control", "control", "stop", "stop"], 1))
        self.assertEqual((self.spoken(), self.logged), ([], ["стоп: замолкаю"]))


class RestartOnline(unittest.TestCase):
    """A model missing from the offline cache: the companion starts again with the network."""

    def test_how_it_starts_again(self):
        import threading
        from unittest import mock
        exits, calls = [], []

        class Exited(Exception):
            pass

        def exit_(code):
            exits.append(code)
            raise Exited

        def call(args):
            calls.append(args)
            return 7
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(companion, "MODELS_READY", Path(d) / ".models_ready"), \
                mock.patch.object(companion.os, "_exit", exit_), \
                mock.patch("subprocess.call", call), \
                mock.patch.object(companion.sys, "argv", ["bv", "--forever"]), \
                mock.patch.dict(companion.os.environ, {companion.LAUNCHED: "1"}):
            (Path(d) / ".models_ready").touch()
            with self.assertRaises(Exited):
                companion.restart_online(lambda *a: None)       # under the launcher: its exit code
            self.assertEqual(exits, [companion.RESTART])
            self.assertFalse((Path(d) / ".models_ready").exists())
            del companion.os.environ[companion.LAUNCHED]
            # in the console: the same command as a child (arguments as a list - quoted by subprocess,
            # not joined as os.execv does on Windows), waited for, its exit code
            with self.assertRaises(Exited):
                companion.restart_online(lambda *a: None)
            self.assertEqual(calls, [[companion.sys.executable, "-m", "bv", "--forever"]])
            self.assertEqual(exits[-1], 7)
            # off the main thread: left to the main loop, which first stops reading the strip
            worker = threading.Thread(target=companion.restart_online, args=(lambda *a: None,))
            worker.start()
            worker.join()
            self.assertEqual(len(calls), 1)
            self.assertTrue(companion._restart.is_set())
            companion._restart.clear()


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



class ExitCodes(unittest.TestCase):
    def test_the_launcher_knows_ours(self):
        # the launcher does not count these as a failed start of a new version (no rollback for them)
        import ast
        from bv.launcher.process import Companion
        self.assertEqual((companion.RESTART, companion.ALREADY, companion.CONFIG_ERROR),
                         (Companion.RESTART, Companion.ALREADY, Companion.CONFIG_ERROR))
        tree = ast.parse(Path(companion.__file__).read_text(encoding="utf-8"))
        handler = next(n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler)
                       and "ConfigError" in ast.unparse(n.type))
        returned = [ast.unparse(n.value) for n in ast.walk(handler) if isinstance(n, ast.Return)]
        self.assertEqual(returned, ["CONFIG_ERROR"], "a config.json the companion cannot read ends with CONFIG_ERROR")

if __name__ == "__main__":
    unittest.main()
