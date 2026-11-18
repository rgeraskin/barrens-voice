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

    def test_help_of_this_version(self):
        # config.update kept the file's old _help: a corrected text never reached an existing config.json
        old = dict(companion.DEFAULT_CONFIG, _help="players: also takes F5 voice ids (orc-male#60).")
        config, saved, _ = self.load(json.dumps(old))
        self.assertEqual(config["_help"], companion.DEFAULT_CONFIG["_help"])
        self.assertEqual(saved["_help"], companion.DEFAULT_CONFIG["_help"])

    def test_a_file_that_cannot_be_replaced_is_no_reason_not_to_start(self):
        # read-only or held for a moment: the write of new settings / this version's _help raised OSError, main()
        # stopped with CONFIG_ERROR («исправь файл») for a file that read fine, and config.json.tmp stayed
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            mine = json.dumps(dict(companion.DEFAULT_CONFIG, rate=3, _help="the text of the version before"))
            path.write_text(mine, encoding="utf-8")
            for failure in ({"target": "os.replace"}, {"target": "pathlib.Path.write_text"}):
                logged = []
                with self.subTest(**failure), mock.patch(failure["target"], side_effect=PermissionError(13, "Access is denied")):
                    config, stamp = companion.load_config_stamped(path, logged.append)
                self.assertEqual(config["rate"], 3)                                   # the settings as read
                self.assertEqual(config["_help"], companion.DEFAULT_CONFIG["_help"])
                self.assertEqual(stamp, companion._stamp(path))                       # the file as it is: watched
                self.assertEqual(path.read_text(encoding="utf-8"), mine)
                self.assertEqual(sorted(p.name for p in Path(d).iterdir()), ["config.json"])   # no .tmp left
                self.assertEqual(len(logged), 1)
                self.assertIn("не удалось записать config.json (Access is denied)", logged[0])
                from bv.logs import level_of
                self.assertEqual(level_of(logged[0]), "WARN")
            path.unlink()
            with mock.patch("os.replace", side_effect=PermissionError(13, "Access is denied")):
                self.assertEqual(companion.load_config_stamped(path, lambda *a: None), (companion.DEFAULT_CONFIG, None))
            self.assertEqual(list(Path(d).iterdir()), [])                             # none made, none left over

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

    def test_numbers_that_are_no_numbers(self):
        # "inf" raised OverflowError before state.init, NaN and 1e999 (Infinity) were kept, a pace limit of 0
        # divided by zero in every F5 line, a null gain killed the F5 thread
        huge = "1" + "0" * 400                          # an integer no float holds
        config, saved, logged = self.load(
            '{"max_queue": "inf", "f5_margin": NaN, "f5_tail": "nan", "volume": 1e999, "rate": -Infinity, '
            f'"log_keep_days": {huge}, "voice_pace_limit": 0, "onnx_threads": 0, "voice_pace_quantile": -3, '
            '"same_speaker_gap": true, '
            '"capture_height": 2.5, "kind_gain_db": null, "players": null, "voice_shifts": "1.5", '
            '"question_intonation": 5}')
        default = companion.DEFAULT_CONFIG
        for key in ("max_queue", "f5_margin", "f5_tail", "volume", "rate", "log_keep_days", "same_speaker_gap",
                    "kind_gain_db", "players", "voice_shifts", "question_intonation"):
            self.assertEqual(config[key], default[key], key)
        self.assertEqual((config["voice_pace_limit"], config["onnx_threads"], config["voice_pace_quantile"]), (1.0, 1, 0))
        self.assertEqual(config["capture_height"], 2)  # an int setting stays an int
        self.assertEqual(len(logged), 14, logged)
        from bv.logs import level_of
        self.assertEqual({level_of(m) for m in logged}, {"WARN"})
        self.assertIn("не удалось прочитать «kind_gain_db» в config.json (None): беру {\"yell\": 3", "\n".join(logged))
        from bv.f5engine import line_seconds
        line_seconds(0.2, 0.1, 40, 100, "Тралл", config)  # a slow voice with the pace limit settled
        json.dumps(config, allow_nan=False)             # nothing that is no finite number is left


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
            self.assertIs(config["exit_with_wow"], True, text)
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

    def test_the_launchers_window_reaches_it_through_live_json(self):
        # config.json read-only: the launcher's window writes tmp/live.json; the last of the two files changed wins
        import os
        with tempfile.TemporaryDirectory() as d:
            path, live_path = Path(d) / "config.json", Path(d) / "live.json"
            path.write_text(json.dumps({"exit_with_wow": True}), encoding="utf-8")
            config = {"exit_with_wow": True}
            live = companion.LiveConfig(config, path, None, live_path)
            live.refresh()
            self.assertIs(config["exit_with_wow"], True)                  # no live.json yet: the file's
            companion.write_live({"exit_with_wow": False, "rate": 3}, live_path)
            self.assertEqual(json.loads(live_path.read_text(encoding="utf-8")), {"exit_with_wow": False})
            live.refresh()
            self.assertIs(config["exit_with_wow"], False)
            live.refresh()
            self.assertIs(config["exit_with_wow"], False)                 # unchanged files: nothing read again
            path.write_text(json.dumps({"exit_with_wow": True}), encoding="utf-8")   # edited by hand later
            os.utime(path, ns=(10**18, 10**18))
            live.refresh()
            self.assertIs(config["exit_with_wow"], True)
            live_path.write_text("{half", encoding="utf-8")                # broken: kept as it was
            os.utime(live_path, ns=(2 * 10**18, 2 * 10**18))
            live.refresh()
            self.assertIs(config["exit_with_wow"], True)
            # a companion not started by the launcher has no live file to read
            config2 = {"exit_with_wow": True}
            companion.write_live({"exit_with_wow": False}, live_path)
            companion.LiveConfig(config2, path, None, None).refresh()
            self.assertIs(config2["exit_with_wow"], True)

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

    def test_a_battle_net_friend_logged_without_the_digits(self):
        self.line("Вася шепчет:\x04 ты где?", kind="whisper", sender="BN:Вася#1234", raw="ты где?")
        self.assertEqual(self.logged[0], "[шёпот] BN:Вася (Orc, м) → orc-male: Вася шепчет: ТЫ ГДЕ?")
        self.assertNotIn("#1234", "\n".join(self.logged))
        self.assertEqual(self.speaker.said[0].sender, "BN:Вася#1234")     # the voice: by the whole BattleTag

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

    def test_no_temporary_file_left_when_the_swap_fails(self):
        # the game holding the file open: VoiceList.lua.tmp stayed in the addon's folder
        from unittest import mock

        from bv import paths
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "VoiceList.lua"
            path.write_text("a = 1\n", encoding="utf-8")
            with mock.patch.object(paths.os, "replace", side_effect=PermissionError("in use")), \
                    self.assertRaises(PermissionError):
                paths.write_if_changed(path, "a = 2\n")
            self.assertEqual([p.name for p in Path(d).iterdir()], ["VoiceList.lua"])
            self.assertEqual(path.read_text(encoding="utf-8"), "a = 1\n")

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


class GameRunning(unittest.TestCase):
    """A program named like the game whose path cannot be read: the game for the launch (no second game
    started), not for the exit with the game (a tool such as WowUp.exe must not keep the companion)."""

    def processes(self, readable, unreadable):
        def process_paths(match, unread=None):
            if unread is not None:
                unread.extend(name for name in unreadable if match(name))
            return [p for p in readable if match(p.replace("\\", "/").rsplit("/", 1)[-1])]
        return process_paths

    def test_unreadable(self):
        from unittest import mock

        from bv import launch
        game = r"D:\Games\World of Warcraft\_forever_\Wow.exe"
        for readable, unreadable, running, may_run in (
                ([], [], False, False),
                ([game], [], True, True),
                ([r"C:\Programs\WowUp\WowUp.exe"], [], False, False),
                ([], ["Wow.exe"], False, True),                  # its path hidden from this user: may be the game
                ([], ["WOW.EXE"], False, True),
                ([], ["WowUp.exe"], False, False),               # another account's tool: no game, the launch stays open
                ([], ["wowreg32.exe"], False, False),            # Windows' own, run as SYSTEM
                ([], ["Battle.net.exe"], False, False)):         # only names like the game's count
            with mock.patch.object(launch, "process_paths", self.processes(readable, unreadable)):
                self.assertEqual((launch.wow_running(), launch.wow_may_run()), (running, may_run),
                                 (readable, unreadable))

    def test_no_second_game(self):
        # launch() asked wow_running: a Wow.exe it could not read was no game, and Battle.net started a second one
        from unittest import mock

        from bv import launch
        logged, sent = [], []
        with mock.patch.object(launch, "process_paths", self.processes([], ["Wow.exe"])), \
                mock.patch.object(launch.sys, "platform", "win32"), \
                mock.patch.object(launch, "find_battlenet", lambda config: sent.append(1)):
            self.assertFalse(launch.launch({}, logged.append))
        self.assertEqual((logged, sent), (["игра уже запущена — второй раз не запускаю"], []))

    def test_the_start_says_why_it_does_not_launch(self):
        # the gate in main() closed without a word: Play started no game and the log said nothing
        from unittest import mock

        from bv import launch
        game = r"D:\Games\World of Warcraft\_forever_\Wow.exe"
        for readable, unreadable, allowed, said in (
                ([], [], True, []),
                ([], ["WowUp.exe", "wowreg32.exe"], True, []),
                ([game], [], False, [f"игру не запускаю: она уже запущена ({game})"]),
                ([], ["Wow.exe"], False, ["игру не запускаю: уже запущена Wow.exe, но откуда, не видно "
                                          "(её запустили от администратора или под другим пользователем)"])):
            logged = []
            with mock.patch.object(launch, "process_paths", self.processes(readable, unreadable)):
                self.assertIs(launch.launch_allowed(logged.append), allowed, (readable, unreadable))
            self.assertEqual(logged, said)



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
