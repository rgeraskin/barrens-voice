"""The companion's own plumbing that runs without Windows: config.json, service frames and chat lines,
the files it writes into the addon."""
import inspect
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
                    config = companion.load_config(path, logged.append)
                self.assertEqual(config["rate"], 3)                                   # the settings as read
                self.assertEqual(config["_help"], companion.DEFAULT_CONFIG["_help"])
                self.assertEqual(path.read_text(encoding="utf-8"), mine)
                self.assertEqual(sorted(p.name for p in Path(d).iterdir()), ["config.json"])   # no .tmp left
                self.assertEqual(len(logged), 1)
                self.assertIn("не удалось записать config.json (Access is denied)", logged[0])
                from bv.logs import level_of
                self.assertEqual(level_of(logged[0]), "WARN")
            path.unlink()
            with mock.patch("os.replace", side_effect=PermissionError(13, "Access is denied")):
                self.assertEqual(companion.load_config(path, lambda *a: None), companion.DEFAULT_CONFIG)
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


class GameWatch(unittest.TestCase):
    def test_the_voice_over_ends_with_the_game(self):
        # «Закрываться вместе с игрой» off kept the race voices in video memory until the next game: the
        # voice-over now always ends some 10 s after the game it saw, whatever config.json says
        running = [False]
        watch = companion.GameWatch(lambda: running[0])
        self.assertFalse(watch.closed(0.0))                 # no game seen yet: it waits for one
        self.assertFalse(watch.closed(100.0))
        running[0] = True
        self.assertFalse(watch.closed(103.0))
        running[0] = False
        self.assertFalse(watch.closed(104.0))               # looked at every 2 s only
        self.assertFalse(watch.closed(106.0))               # gone: the 10 s start
        self.assertFalse(watch.closed(112.0))
        running[0] = True                                   # back (a client restarting itself): no end
        self.assertFalse(watch.closed(115.0))
        running[0] = False
        self.assertFalse(watch.closed(118.0))
        self.assertFalse(watch.closed(127.0))
        self.assertTrue(watch.closed(130.0))
        self.assertNotIn("exit_with_wow", inspect.getsource(companion.GameWatch))


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
        self.assertEqual(calls, ["set_place", "remember"])       # kept for a restart mid-game too
        self.assertTrue(logged[0].startswith("полоска: верх"), logged)


class LiveVolumeFrame(unittest.TestCase):
    def test_a_settings_frame_sets_the_volume_at_once(self):
        # the mouse wheel over the minimap button sends a settings frame: its volume reaches the line playing
        import types
        from unittest import mock
        from bv import __main__ as companion
        from bv.protocol import Line
        gains = []
        player = types.SimpleNamespace(set_gain=gains.append)
        engines = types.SimpleNamespace(config={"volume": 100})
        capturer = types.SimpleNamespace(place=None, set_place=lambda p: None, remember=lambda p: None)
        with mock.patch.object(companion, "log", lambda *a: None):
            companion.service(Line("control", "", "", "", "", "", "-", volume=60), True, engines, player, None, capturer)
            companion.service(Line("control", "", "", "", "", "", "-"), True, engines, player, None, capturer)
        self.assertEqual(gains, [0.6])                         # a frame without a volume changes nothing


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

    def test_a_chat_lines_volume_in_the_order_frames_come(self):
        # the volume asked is set as each frame comes, a chat line's too: a line made before a turn of the wheel does not
        # take the volume back when it is queued later (the player reads the volume as it plays)
        import types
        from bv.protocol import Line
        gains = []
        self.lines.player = types.SimpleNamespace(set_gain=gains.append)
        self.config["volume"] = 100
        self.lines.handle(Line("party", "Тралл", "Orc", "2", "SHAMAN", "", "Тралл:\x04 раз", volume=120), False)
        self.lines.handle(Line("party", "Тралл", "Orc", "2", "SHAMAN", "", "Тралл:\x04 два"), False)   # none sent
        self.assertEqual(gains, [1.2])
        self.lines.handle(Line("someday", "Тралл", "Orc", "2", "SHAMAN", "", "x", volume=50), False)   # a newer kind
        self.assertEqual(gains, [1.2], "an unknown kind sets nothing")

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
                                           "строки типа «future» не озвучиваю (аддон новее лаунчера?)"])
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
        exits, calls, envs = [], [], []

        class Exited(Exception):
            pass

        def exit_(code):
            exits.append(code)
            raise Exited

        def call(args, env=None):
            calls.append(args)
            envs.append(env)
            return 7
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(companion, "MODELS_READY", Path(d) / ".models_ready"), \
                mock.patch.object(companion.os, "_exit", exit_), \
                mock.patch("subprocess.call", call), \
                mock.patch.object(companion.sys, "argv", ["bv", "--forever"]), \
                mock.patch.dict(companion.os.environ, {companion.LAUNCHED: "1", "HF_HUB_OFFLINE": "1",
                                                       "TRANSFORMERS_OFFLINE": "1", companion.LAUNCHED + "_PROBE": "kept"}):
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
            # ... online: offline_models' variables not handed down (they made the child fail at once)
            self.assertNotIn("HF_HUB_OFFLINE", envs[-1])
            self.assertNotIn("TRANSFORMERS_OFFLINE", envs[-1])
            self.assertEqual(envs[-1].get(companion.LAUNCHED + "_PROBE"), "kept")
            # off the main thread: left to the main loop, which first stops reading the strip
            worker = threading.Thread(target=companion.restart_online, args=(lambda *a: None,))
            worker.start()
            worker.join()
            self.assertEqual(len(calls), 1)
            self.assertTrue(companion._restart.is_set())
            companion._restart.clear()


    def test_ruaccent_offline_error_is_a_detail(self):
        # beta 21: a cut RUAccent download cleared offline, then «RUAccent: Cannot reach … offline mode» in red
        # in the launcher's window for a start that mends itself online: DEBUG offline, the error up online
        from bv.logs import level_of

        class Failing:
            def load(self):
                raise OSError("Cannot reach https://huggingface.co/api/models/ruaccent/accentuator: offline mode is enabled")
        for offline in (True, False):
            logged, restarts = [], []
            with self.subTest(offline=offline), self.assertRaises(OSError):
                companion.load_accentor(Failing(), offline, lambda m, level=None: logged.append((m, level)),
                                        restart=restarts.append)
            if offline:
                self.assertEqual([lvl for _, lvl in logged], ["DEBUG"])
                self.assertTrue(logged[0][0].startswith("RUAccent: Cannot reach"))
                self.assertEqual(len(restarts), 1)
                self.assertEqual(level_of(logged[0][0]), "ERROR")      # what it was without the level
            else:
                self.assertEqual((logged, restarts), ([], []))         # main() ends on it: an ERROR there


class AddonFiles(unittest.TestCase):
    """VoiceList.lua, CompanionStatus.lua, DictionaryOnline.lua and NewsData.lua: written whole or not at all."""

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

class Utf8Output(unittest.TestCase):
    """A console redirected to a file has the code page's encoding: «×» must not raise there. (The test streams
    keep "\n": on Windows a text stream writes "\r\n" by default.)"""

    def test_a_cp1251_stream_takes_any_character(self):
        import io
        from unittest import mock
        out = io.TextIOWrapper(io.BytesIO(), encoding="cp1251", newline="\n")
        err = io.TextIOWrapper(io.BytesIO(), encoding="cp1251", newline="\n")
        with self.assertRaises(UnicodeEncodeError):
            out.write("экран 1920×1080")
        out.seek(0); out.truncate()
        with mock.patch.object(companion.sys, "stdout", out), mock.patch.object(companion.sys, "stderr", err):
            companion.utf8_output()
            print("экран 1920×1080", flush=True)
            err.write("×\n"); err.flush()
        self.assertEqual(out.buffer.getvalue().decode("utf-8"), "экран 1920×1080\n")
        self.assertEqual(err.buffer.getvalue().decode("utf-8"), "×\n")
        companion.utf8_output()                              # a stream without reconfigure: left alone
        # what even UTF-8 cannot write (a lone surrogate, from a broken name): replaced, not raised
        lone = io.TextIOWrapper(io.BytesIO(), encoding="cp1251", newline="\n")
        with mock.patch.object(companion.sys, "stdout", lone), mock.patch.object(companion.sys, "stderr", err):
            companion.utf8_output()
            print("имя \ud800 сломано", flush=True)
        self.assertEqual(lone.buffer.getvalue().decode("utf-8"), "имя ? сломано\n")


if __name__ == "__main__":
    unittest.main()
