"""The engine manager with a fake F5: loaded on demand, notices, unloaded, falls back on error."""
import sys
import threading
import types
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bv.protocol import Line  # noqa: E402


class FakeF5:
    fail = None
    missing = False     # the failure was a model missing from the cache (f5engine.models_missing)
    made = 0

    def __init__(self, *a):
        FakeF5.made += 1
        self.ready = threading.Event()
        self.error = None
        self.stopped = False
        self.cleared = False
        self.assigner = None
        self.lines = __import__("queue").Queue()

    def clear(self):
        self.cleared = True

    def start(self):
        self.error = FakeF5.fail
        self.models_missing = FakeF5.missing
        if FakeF5.fail is not None:          # failed at once; else ready when the test says
            self.ready.set()

    def shutdown(self):
        self.stopped = True


class FakeSapi:
    def __init__(self):
        self.said = []

    def say(self, line):
        self.said.append(line.text)

    def clear(self):
        pass


from bv.engines import Engines  # noqa: E402


def _ort_stand_in():
    """onnxruntime where it is installed; else (Windows without a video card's extra, as in CI: the module comes
    only with onnxruntime-gpu or -directml) a stand-in with what the tests below touch, left in sys.modules for
    the run - a per-test patch of sys.modules would drop numpy and the rest a test loaded, and the next import
    of them fails."""
    try:
        import onnxruntime  # noqa: F401
    except ImportError:
        ort = types.ModuleType("onnxruntime")
        ort.get_available_providers = lambda: ["CPUExecutionProvider"]

        class SessionOptions:
            enable_mem_pattern = True
            graph_optimization_level = None
            execution_mode = None
        ort.SessionOptions = SessionOptions
        ort.GraphOptimizationLevel = types.SimpleNamespace(ORT_ENABLE_ALL=99)
        ort.ExecutionMode = types.SimpleNamespace(ORT_SEQUENTIAL=0)
        sys.modules["onnxruntime"] = ort


_ort_stand_in()

FAKE_F5 = types.SimpleNamespace(F5Speaker=FakeF5)


def wait():
    """Until the engine manager has heard how a load ended (its f5-wait threads are done)."""
    for t in threading.enumerate():
        if t.name == "f5-wait":
            t.join(2)


class EnginesTest(unittest.TestCase):
    def setUp(self):
        # the engine imports F5Speaker when it loads; a fake one only for these tests
        patcher = unittest.mock.patch.dict(sys.modules, {"bv.f5engine": FAKE_F5})
        patcher.start()
        self.addCleanup(patcher.stop)

    def make(self, home=Path("."), clock=None):
        self.sapi = FakeSapi()
        self.logged = []
        return Engines({"engine": "f5", "spoken_notices": True}, self.logged.append, home, self.sapi, None,
                       **({"clock": clock} if clock else {}))

    def test_load_on_demand_then_unload(self):
        FakeF5.fail = None
        e = self.make()
        line = Line("say", "Орк", "Orc", "2", "", "", "текст", 100, "f5")
        self.assertIs(e.for_line(line), self.sapi)          # still loading: Windows voices meanwhile
        e.f5.ready.set()
        wait()
        self.assertIn("Голоса рас готовы.", self.sapi.said)
        self.assertIsInstance(e.for_line(line), FakeF5)
        f5 = e.f5
        e.want("sapi")
        self.assertTrue(f5.stopped)
        self.assertIsNone(e.f5)
        self.assertIn("Голоса рас выгружены.", self.sapi.said)
        sapi_line = Line("say", "Орк", "Orc", "2", "", "", "текст", 100, "sapi")
        self.assertIs(e.for_line(sapi_line), self.sapi)

    def test_failure_falls_back(self):
        FakeF5.fail = "нет CUDA"
        e = self.make()
        e.want("f5")
        wait()
        self.assertIsNone(e.f5)
        self.assertIn("Голоса рас недоступны, читаю голосами Windows.", self.sapi.said)

    def test_online_restart_only_for_a_missing_model(self):
        # TensorRT not starting is no reason to go online and drop the models' mark; a model not in the cache is
        for missing, want in ((False, []), (True, ["нет в кэше"])):
            with self.subTest(missing=missing):
                FakeF5.fail, FakeF5.missing = "нет в кэше", missing
                e = self.make()
                asked = []
                e.on_models_missing = asked.append
                e.want("f5")
                wait()
                self.assertIn("Голоса рас недоступны, читаю голосами Windows.", self.sapi.said)
                self.assertEqual(asked, want)
        FakeF5.missing = False

    def test_an_empty_error_is_still_a_failure(self):
        # str() of some exceptions is "" (StopIteration): never taken for "ready"
        FakeF5.fail = ""
        e = self.make()
        e.want("f5")
        wait()
        self.assertFalse(e.ready)
        self.assertIsNone(e.f5)
        self.assertNotIn("Голоса рас готовы.", self.sapi.said)
        line = Line("say", "Орк", "Orc", "2", "", "", "текст", 100, "f5")
        self.assertIs(e.for_line(line), self.sapi)


    def test_a_failed_load_is_not_started_again_for_every_line(self):
        from bv import engines
        FakeF5.fail, FakeF5.made = "нет CUDA", 0
        now = [0.0]
        e = self.make(clock=lambda: now[0])
        line = Line("say", "Орк", "Orc", "2", "", "", "текст", 100, "f5")
        for _ in range(5):                                  # each frame and line asks for F5
            e.want("f5")
            self.assertIs(e.for_line(line), self.sapi)
            wait()
        self.assertEqual(FakeF5.made, 1)
        self.assertEqual(self.sapi.said.count("Голоса рас недоступны, читаю голосами Windows."), 1)
        now[0] = engines.RETRY_AFTER + 1                    # a while later: tried once more
        e.want("f5")
        wait()
        e.want("f5")
        wait()
        self.assertEqual(FakeF5.made, 2)
        e.want("sapi")                                      # the addon switched to Windows voices and back
        e.want("f5")
        wait()
        self.assertEqual(FakeF5.made, 3)

    def test_unloaded_stopped_or_reset_while_loading(self):
        import tempfile
        FakeF5.fail = None
        with tempfile.TemporaryDirectory() as d:
            e = self.make(home=Path(d))
            e.want("f5")
            loading = e.f5
            e.stop()                                        # a stop while loading: its queue is dropped
            self.assertTrue(loading.cleared)
            (Path(d) / "assignments.json").write_text("{}", encoding="utf-8")
            e.reset_assignments()                           # no assigner yet: the file is forgotten
            self.assertFalse((Path(d) / "assignments.json").exists())
            e.want("sapi")                                  # unloaded before it was ready
            self.assertTrue(loading.stopped)
            self.assertIn("загрузка голосов рас отменена", self.logged)
            loading.ready.set()                             # its load ends after all: nobody listens
            wait()
            self.assertFalse(e.ready)
            self.assertIsNone(e.f5)
            self.assertNotIn("Голоса рас готовы.", self.sapi.said)


    def test_a_windows_voice_sample_keeps_the_race_voices(self):
        # the voices window's play button: voice=sapi;sapi=<name> for that test line only
        FakeF5.fail = None
        e = self.make()
        e.follow(Line("control", "", "", "", "", "", "", 100, "f5"))
        loaded = e.f5
        self.assertIsNotNone(loaded)
        sample = Line("test", "Проверка", "", "", "", "", "Привет!", 100, "sapi", sapi_voice="Irina")
        e.follow(sample)
        self.assertIs(e.f5, loaded)
        self.assertFalse(loaded.stopped)
        self.assertIs(e.for_line(sample), self.sapi)       # the sample itself in that Windows voice
        e.follow(Line("control", "", "", "", "", "", "", 100, "sapi"))   # the addon switched: unloaded
        self.assertTrue(loaded.stopped)
        loaded.ready.set()
        wait()


class Accent:
    def accent(self, text):
        return text.replace("о", "+о")          # stress marks: the bytes F5 is given are more than typed

    def load(self):
        pass


class F5SpeakerLoad(unittest.TestCase):
    """F5Speaker's own thread with ONNX Runtime and the game client faked (they are Windows only)."""

    def speaker(self, home, slots, onnx=None, player=None):
        from bv import f5engine
        from bv.__main__ import DEFAULT_CONFIG
        from bv.assign import Assigner
        logged = []
        speaker = f5engine.F5Speaker(dict(DEFAULT_CONFIG), logged.append, home, Accent(),
                                     player=player or types.SimpleNamespace(generation=0))

        def load_onnx():
            speaker.assigner = Assigner(slots, home / "assignments.json", {})
            speaker.onnx, speaker.ref_audio, speaker.device = onnx, {}, "test"
        speaker._load_onnx = load_onnx
        return speaker, logged

    def voice(self, home, speech=2.0):
        """One voice of the bank: a 3 s reference clip with 2 s of speech in it."""
        import numpy as np
        import soundfile as sf
        from bv.gamevoices import Slot
        path = home / "orc-male.wav"
        sf.write(str(path), np.zeros(72000, dtype="float32"), 24000)
        return Slot("orc-male", "orc-male", "orc", "male", 0.0, str(path), "Мне это не по силам.", speech)

    def test_the_banks_pace_in_the_units_of_a_line(self):
        # the target pace counted the reference's bytes without stress marks, a voice's own pace with
        # them: the same voice was drawn toward itself by ~7 %
        import tempfile
        from bv import f5engine

        class Onnx:
            in_rate = 24000

            def synth(self, ref_audio, ref_text, text, total):
                return __import__("numpy").zeros(2400, dtype="float32"), 24000
        with tempfile.TemporaryDirectory() as d:
            slot = self.voice(Path(d))
            speaker, _ = self.speaker(Path(d), [slot], Onnx())
            speaker._load()
            # the unit: seconds of speech per byte of the reference's text as F5 gets it, stress marks
            # included - as a line is counted (its text is stressed before `duration`)
            stressed = Accent().accent(slot.text).encode("utf-8")
            self.assertGreater(len(stressed), len(slot.text.encode("utf-8")))
            self.assertAlmostEqual(speaker.pace(slot), slot.speech / len(stressed))
            self.assertAlmostEqual(speaker.target_pace, speaker.pace(slot))
            config = speaker.config
            text = "Привет всем"
            expected = 3.0 + f5engine.line_seconds(speaker.pace(slot), 0.0, len(text.encode("utf-8")), 100, "",
                                                   {**config, "character_tempo": 0})
            config["character_tempo"] = 0
            self.assertAlmostEqual(speaker.duration(slot, text, 100), expected)   # its own pace: not drawn

    def test_a_line_from_the_queue_to_the_player(self):
        import tempfile

        import numpy as np
        made, played = [], []

        class Onnx:
            in_rate = 24000

            def synth(self, ref_audio, ref_text, text, total):
                made.append(text)
                tone = np.sin(np.arange(24000) / 24000 * 2 * np.pi * 200).astype("float32") * 0.3
                return np.concatenate([tone, np.zeros(4800, dtype="float32")]), 24000

        class Player:
            generation = 0

            def play(self, data, generation, received=None):
                played.append((data[:4], generation))
        from unittest import mock
        from bv import f5engine
        made_at = []
        real_wav_bytes = f5engine.wav_bytes

        def wav_bytes(samples, rate, volume, gain_db=0.0, tail=f5engine.TAIL):
            made_at.append(volume)
            return real_wav_bytes(samples, rate, volume, gain_db, tail)
        self.addCleanup(lambda: self.assertTrue(made_at and all(v == 1.0 for v in made_at),
                                                f"lines made at full loudness, the player applies the volume: {made_at}"))
        patcher = mock.patch.object(f5engine, "wav_bytes", wav_bytes)
        patcher.start()
        self.addCleanup(patcher.stop)
        with tempfile.TemporaryDirectory() as d:
            speaker, logged = self.speaker(Path(d), [self.voice(Path(d))], Onnx(), Player())
            loop = threading.Thread(target=speaker._synth_loop)
            loop.start()
            self.assertTrue(speaker.ready.wait(5))
            self.assertIsNone(speaker.error)
            # the addon's volume at 50 %: the line is still made at full loudness, the player applies the 50 %
            speaker.say(Line("say", "Громмаш", "Orc", "2", "", "", "Кто в рейд", 100, "f5", volume=50))
            speaker.lines.put(None)                  # the end, after that line
            loop.join(5)
            self.assertFalse(loop.is_alive())
        self.assertEqual(made, ["Проверка.", "Кт+о в рейд."])   # the warm-up; the line stressed, a full stop
        self.assertIsNone(speaker.onnx)              # the model freed at the end
        self.assertEqual(played, [(b"RIFF", 0)])

    def test_the_first_sentence_plays_while_the_rest_is_made(self):
        # f5_first_sentence (on by default): the first sentence goes to the player made on its own, with the short gap
        # for its tail, the rest after it as one; its arrival goes with it for the log's «до звука». Off: one piece
        import tempfile
        import time

        import numpy as np
        from bv import f5engine
        made, played, tails = [], [], []

        class Onnx:
            in_rate = 24000

            def synth(self, ref_audio, ref_text, text, total):
                made.append(text)
                tone = np.sin(np.arange(2400) / 24000 * 2 * np.pi * 200).astype("float32") * 0.3
                return np.concatenate([tone, np.zeros(4800, dtype="float32")]), 24000

        class Player:
            generation = 0

            def play(self, data, generation, received=None):
                played.append(received)
        real_wav_bytes = f5engine.wav_bytes

        def wav_bytes(samples, rate, volume, gain_db=0.0, tail=f5engine.TAIL):
            tails.append(tail)
            return real_wav_bytes(samples, rate, volume, gain_db, tail)
        patcher = unittest.mock.patch.object(f5engine, "wav_bytes", wav_bytes)
        patcher.start()
        self.addCleanup(patcher.stop)
        for first in (True, False):
            tails.clear()
            made.clear()
            played.clear()
            with tempfile.TemporaryDirectory() as d:
                speaker, _ = self.speaker(Path(d), [self.voice(Path(d))], Onnx(), Player())
                speaker.config["f5_first_sentence"] = first
                loop = threading.Thread(target=speaker._synth_loop)
                loop.start()
                self.assertTrue(speaker.ready.wait(5))
                line = Line("say", "Громмаш", "Orc", "2", "", "", "Привет. Кто в рейд? Идём", 100, "f5")
                speaker.say(line)
                speaker.lines.put(None)
                loop.join(5)
            self.assertLess(line.received, time.monotonic())
            self.assertEqual(made[1:], ["Привет.", "Кт+о в рейд?", "Идём."])           # each group made once
            if first:
                self.assertEqual(played, [line.received, None])
                self.assertEqual(tails, [f5engine.GAP, f5engine.TAIL])                  # the part's tail: the gap
            else:
                self.assertEqual(played, [line.received])
                self.assertEqual(tails, [f5engine.TAIL])
        # a line longer than f5_part_seconds: cut at its commas, each piece its own part, the gap between
        tails.clear()
        made.clear()
        played.clear()
        with tempfile.TemporaryDirectory() as d:
            speaker, _ = self.speaker(Path(d), [self.voice(Path(d))], Onnx(), Player())
            speaker.config.update(f5_first_sentence=False, f5_part_seconds=4)
            speaker.duration = lambda slot, text, rate, character="": speaker.ref_seconds[slot.id] + len(text.split())
            loop = threading.Thread(target=speaker._synth_loop)
            loop.start()
            self.assertTrue(speaker.ready.wait(5))
            line = Line("say", "Громмаш", "Orc", "2", "", "", "раз два три, четыре пять шесть, семь", 100, "f5")
            speaker.say(line)
            speaker.lines.put(None)
            loop.join(5)
        self.assertEqual([len(text.split()) for text in made[1:]], [3, 4])
        self.assertTrue(made[1].endswith(","), made)
        self.assertEqual(played, [line.received, None])
        self.assertEqual(tails, [f5engine.GAP, f5engine.TAIL])
        # the estimate at the line's speed and for its sender: 6 words at 200 % fit 3 s for Громмаш - one piece; at
        # 100 %, or for another name (three times slower here), they would be cut
        made.clear()
        with tempfile.TemporaryDirectory() as d:
            speaker, _ = self.speaker(Path(d), [self.voice(Path(d))], Onnx(), Player())
            speaker.config.update(f5_first_sentence=False, f5_part_seconds=3)
            speaker.duration = lambda slot, text, rate, character="": (
                speaker.ref_seconds[slot.id] + len(text.split()) * 100 / rate * (1 if character == "Громмаш" else 3))
            loop = threading.Thread(target=speaker._synth_loop)
            loop.start()
            self.assertTrue(speaker.ready.wait(5))
            speaker.say(Line("say", "Громмаш", "Orc", "2", "", "", "раз два три, четыре пять шесть", 200, "f5"))
            speaker.lines.put(None)
            loop.join(5)
        self.assertEqual(len(made[1:]), 1, made)
        # and with the first sentence on (the default): the rest, the long one, cut too
        tails.clear()
        made.clear()
        with tempfile.TemporaryDirectory() as d:
            speaker, _ = self.speaker(Path(d), [self.voice(Path(d))], Onnx(), Player())
            speaker.config.update(f5_part_seconds=4)
            speaker.duration = lambda slot, text, rate, character="": speaker.ref_seconds[slot.id] + len(text.split())
            loop = threading.Thread(target=speaker._synth_loop)
            loop.start()
            self.assertTrue(speaker.ready.wait(5))
            speaker.say(Line("say", "Громмаш", "Orc", "2", "", "", "Всем привет в чате. раз два три, четыре пять шесть, семь",
                             100, "f5"))
            speaker.lines.put(None)
            loop.join(5)
        self.assertEqual([len(text.split()) for text in made[1:]], [4, 3, 4])
        self.assertEqual(tails, [f5engine.GAP, f5engine.GAP, f5engine.TAIL])
        cut = f5engine.first_and_rest
        self.assertEqual(cut("Один."), ["Один."])
        self.assertEqual(cut("Раз! Два. Три?"), ["Раз! Два.", "Три?"])             # where the groups part anyway
        self.assertEqual(cut("привет. го в данж."), ["привет. го в данж."])       # a word ahead: not worth a call
        self.assertEqual(cut("ну. не знаю."), ["ну. не знаю."])
        self.assertEqual(cut("Собираемся у входа в Мёртвые копи. Танк уже там, ждём хила."),
                         ["Собираемся у входа в Мёртвые копи.", "Танк уже там, ждём хила."])
        self.assertEqual(cut("Собираемся у входа в копи. Ждём."), ["Собираемся у входа в копи. Ждём."])
        # the first sentence end with four words on each side, not only the first one
        self.assertEqual(cut("ладно… пойду я спать наверное. завтра рано вставать на работу."),
                         ["ладно… пойду я спать наверное.", "завтра рано вставать на работу."])
        self.assertEqual(cut("Собираемся у входа в Мёртвые копи. Танк уже там, ждём хила. Хил будет через пять минут."),
                         ["Собираемся у входа в Мёртвые копи.", "Танк уже там, ждём хила. Хил будет через пять минут."])
        self.assertEqual(cut(""), [])                                              # nothing to say: no F5 call
        self.assertEqual(cut("   "), [])
        self.assertEqual(cut(")."), [])

    def test_a_long_part_is_cut_where_a_speaker_pauses(self):
        # within(): at most `limit` seconds a piece - sentence ends first, then commas and dashes, a word gap last;
        # pieces joined back while they fit
        from bv.f5engine import within

        def words(text):
            return len(text.split())          # a second a word

        def words_or_long(text):
            return sum(9 if len(word) > 10 else 1 for word in text.split())
        self.assertEqual(within("раз два три", words, 4), ["раз два три"])
        self.assertEqual(within("один два три. четыре пять шесть. семь", words, 4),
                         ["один два три.", "четыре пять шесть. семь"])
        self.assertEqual(within("a1 a2 a3, b1 b2 b3, c1 c2 c3. Иду", words, 4),
                         ["a1 a2 a3,", "b1 b2 b3,", "c1 c2 c3. Иду"])
        # a dash ending a piece becomes a comma; the line's own end keeps it
        self.assertEqual(within("раз два три — четыре пять шесть", words, 4), ["раз два три,", "четыре пять шесть"])
        self.assertEqual(within("а б, в г. д е, ж з", words, 4), ["а б, в г.", "д е, ж з"])       # sentence ends first
        self.assertEqual(within("а; б в г: д е", words, 3), ["а;", "б в г:", "д е"])
        self.assertEqual(within("а б: в г д е ж", words, 4), ["а б:", "в г д", "е ж"])
        self.assertEqual(within("раз два три - четыре пять шесть", words, 4), ["раз два три,", "четыре пять шесть"])
        self.assertTrue(within("раз два три четыре пять —", words, 3)[-1].endswith(" —"))
        # a cut between words not after «и», «не», «в»: the words leaning on the next go with it
        self.assertEqual(within("раз два и три четыре пять", words, 3), ["раз два", "и три четыре", "пять"])
        self.assertEqual(within("знает тактику и не ливает после", words, 4), ["знает тактику", "и не ливает после"])
        self.assertEqual(within("иду в данж", words, 2), ["иду", "в данж"])
        self.assertEqual(within("раз два три и не четыре пять", words, 4), ["раз два три", "и не четыре пять"])
        self.assertEqual(within("раз два И три четыре пять", words, 3), ["раз два", "И три четыре", "пять"])
        self.assertEqual(within("wts меч and щит кольцо", words, 3), ["wts меч", "and щит кольцо"])
        self.assertEqual(within("раз два чт+обы три четыре пять", words, 3), ["раз два", "чт+обы три четыре", "пять"])
        self.assertEqual(within("он сказал же что придёт", words, 3), ["он сказал же", "что придёт"])   # leans back
        self.assertEqual(within("раз два, — три четыре пять", words, 3), ["раз два,", "три четыре пять"])
        self.assertEqual(within("и в на с", words, 2), ["и в", "на с"])              # nothing else to cut at: as it was
        pieces = within("— — раз два три четыре пять", words, 3)            # a first piece without a letter too
        self.assertEqual(" ".join(pieces), "— — раз два три четыре пять")
        self.assertTrue(all(any(ch.isalnum() for ch in piece) for piece in pieces), pieces)
        # even runs by bytes, as the estimate counts - not by letters or words
        self.assertEqual(within("ааааа ббббб abc def ghi jkl", lambda t: len(t.encode()), 30),
                         ["ааааа ббббб", "abc def ghi jkl"])
        # a word alone over the limit: on its own, the words around it in runs that fit - not a call a word
        self.assertEqual(within("го в данж " + "ха" * 20 + " кто со мной", words_or_long, 4),
                         ["го в данж", "ха" * 20, "кто со мной"])
        self.assertEqual(within("аб вг ддддддддд", lambda t: len(t.encode()), 9), ["аб вг", "ддддддддд"])
        # only a short sentence (under four words) goes with the next one's head
        self.assertEqual(within("раз два три четыре! a1 a2, b1 b2, c1 c2, d1 d2", words, 6),
                         ["раз два три четыре!", "a1 a2, b1 b2, c1 c2,", "d1 d2"])
        self.assertEqual(within("раз два три — —", words, 4), ["раз два три — —"])       # no piece without a letter
        # a short sentence goes with the head of a long one after it, not alone
        self.assertEqual(within("Внимание! раз два, три четыре, пять шесть", words, 4),
                         ["Внимание! раз два,", "три четыре, пять шесть"])
        self.assertEqual(within("пять-шесть семь-восемь девять-десять", words, 2), ["пять-шесть семь-восемь",
                                                                                     "девять-десять"])
        self.assertEqual(within("1 2 3 4 5 6 7 8 9", words, 4), ["1 2 3", "4 5 6", "7 8 9"])     # even, no lone «9»
        self.assertEqual(within("1 2 3 4 5", words, 4), ["1 2 3", "4 5"])
        self.assertEqual(within("слово", words, 0), ["слово"])                 # nothing left to cut: as it is
        line = ("LFW Enchanting: boots плюс восемь процентов run or плюс семь AGI/STA, all пять neck enchants, bracers "
                "плюс шестнадцать SP, gloves плюс пятнадцать STR, cloak плюс пять AGI & more. PST!")
        pieces = within(line, words, 12)
        self.assertEqual(" ".join(pieces), line)
        self.assertTrue(all(words(piece) <= 12 for piece in pieces), pieces)
        self.assertTrue(pieces[-1].endswith("& more. PST!"), pieces)          # «PST!» with the words before it
        from bv import __main__, f5engine
        self.assertEqual((__main__.DEFAULT_CONFIG["f5_part_seconds"], f5engine.PART_SECONDS), (15.0, 15.0))
        config = {**__main__.DEFAULT_CONFIG, "f5_part_seconds": 0}
        __main__.settle_numbers(config, lambda message: None)
        self.assertEqual(config["f5_part_seconds"], 5.0)               # not a call a word

    def test_f5_steps_from_the_settings(self):
        # f5_steps (the launcher's «Голоса рас»): 10 the shipped model (the cache's other files gone); 8 or 6 the
        # Transformer rewritten (f5_schedule, into the cache), another number's file removed; a number it does not
        # know, or any failure of the rewrite: said, and 10
        import tempfile
        from bv import f5_schedule, f5onnx, paths
        with tempfile.TemporaryDirectory() as d:
            speaker, logged = self.speaker(Path(d), [self.voice(Path(d))])
            models, cache = Path(d) / "models", Path(d) / "cache"
            made = []

            def transformer(source, folder, steps):
                made.append((source, folder.name, steps))
                folder.mkdir(parents=True, exist_ok=True)
                target = folder / f"F5_Transformer-{steps}.onnx"
                target.write_bytes(b"model")
                (folder / f"F5_Transformer-{steps}.onnx.source").write_text("note")
                return target
            with unittest.mock.patch.object(paths, "CACHE_DIR", cache), \
                    unittest.mock.patch.object(f5onnx, "transformer_file", lambda m: m / "F5_Transformer.onnx"), \
                    unittest.mock.patch.object(f5_schedule, "transformer", transformer):
                speaker.config["f5_steps"] = 8
                speaker.fewer_steps(models)
                speaker.config["f5_steps"] = 6
                path, steps = speaker.fewer_steps(models)
                self.assertEqual((path.name, steps), ("F5_Transformer-6.onnx", 6))
                self.assertEqual(made[-1], (models / "F5_Transformer.onnx", "f5-steps", 6))
                self.assertEqual(sorted(p.name for p in (cache / "f5-steps").iterdir()),
                                 ["F5_Transformer-6.onnx", "F5_Transformer-6.onnx.source"])   # 8's 660 MB gone
                (cache / "f5-steps" / "F5_Transformer-8.onnx").write_bytes(b"held")    # an antivirus holds it
                real_unlink = Path.unlink

                def held(path, missing_ok=False):
                    if path.name == "F5_Transformer-8.onnx":
                        raise PermissionError("held")
                    return real_unlink(path, missing_ok=missing_ok)
                with unittest.mock.patch.object(Path, "unlink", held):
                    self.assertEqual(speaker.fewer_steps(models)[1], 6)         # the voices load all the same
                speaker.config["f5_steps"] = 7
                self.assertIsNone(speaker.fewer_steps(models))
                self.assertIn("не удалось взять f5_steps = 7 из config.json: бывает 10, 8, 6, 5 или 4 — беру 10", logged)
                speaker.config["f5_steps"] = 10
                self.assertIsNone(speaker.fewer_steps(models))                       # as shipped, the cache cleared
                self.assertFalse((cache / "f5-steps").exists())
                self.assertEqual(len(made), 3)                                       # 10 asks no rewrite
            for failure in (ValueError("не та модель F5"), MemoryError("onnx.load")):
                with unittest.mock.patch.object(paths, "CACHE_DIR", cache), \
                        unittest.mock.patch.object(f5onnx, "transformer_file", lambda m: m / "F5_Transformer.onnx"), \
                        unittest.mock.patch.object(f5_schedule, "transformer", side_effect=failure):
                    speaker.config["f5_steps"] = 8
                    self.assertIsNone(speaker.fewer_steps(models))
                    self.assertIn(f"не удалось подготовить F5 в 8 шагов: {failure} — беру 10", logged)

    def test_a_bad_gain_costs_the_line_not_the_thread(self):
        # "kind_gain_db": {"yell": null} raised outside the loop's try: the f5-synth thread died, F5 still "ready"
        import tempfile

        import numpy as np
        played = []

        class Onnx:
            in_rate = 24000

            def synth(self, ref_audio, ref_text, text, total):
                return np.sin(np.arange(24000) / 24000 * 2 * np.pi * 200).astype("float32") * 0.3, 24000

        class Player:
            generation = 0

            def play(self, data, generation, received=None):
                played.append(data[:4])
        with tempfile.TemporaryDirectory() as d:
            speaker, logged = self.speaker(Path(d), [self.voice(Path(d))], Onnx(), Player())
            speaker.config["kind_gain_db"] = {"yell": None}
            loop = threading.Thread(target=speaker._synth_loop)
            loop.start()
            self.assertTrue(speaker.ready.wait(5))
            speaker.say(Line("yell", "Громмаш", "Orc", "2", "", "", "За Орду", 100, "f5"))
            speaker.say(Line("say", "Громмаш", "Orc", "2", "", "", "Кто в рейд", 100, "f5"))
            speaker.lines.put(None)
            loop.join(5)
            self.assertFalse(loop.is_alive())
        self.assertEqual(played, [b"RIFF"])                  # the yell lost, the next line said
        self.assertTrue(any(m.startswith("F5-TTS: ") for m in logged), logged)

    def test_an_empty_voice_bank_is_an_error(self):
        # a client without the Russian voice-over: the bank is made with no voices in it. Said before RUAccent
        # and F5's graphs are loaded - a retry every RETRY_AFTER loaded them only to fail
        import tempfile
        from unittest import mock

        from bv import f5engine
        loaded = []

        class Accentor(Accent):
            def load(self):
                loaded.append("RUAccent")
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "F5_Metadata.onnx").write_bytes(b"")
            speaker, _ = self.speaker(Path(d), [])
            del speaker._load_onnx                           # the real one, with ONNX Runtime and the bank faked
            speaker.accentor = Accentor()
            speaker.config.update(f5_onnx_provider="CUDAExecutionProvider", f5_onnx_dir=d)
            with mock.patch("onnxruntime.get_available_providers", lambda: ["CUDAExecutionProvider"]), \
                    mock.patch.object(f5engine, "preload", lambda engine: None), \
                    mock.patch.object(f5engine, "make_bank", lambda *a: []), \
                    mock.patch("bv.f5onnx.F5Onnx", lambda *a: loaded.append("F5")):
                loop = threading.Thread(target=speaker._synth_loop)
                loop.start()
                loop.join(5)
            self.assertFalse(loop.is_alive())
            self.assertTrue(speaker.ready.is_set())
            self.assertIn("русской озвучки", speaker.error)
            self.assertEqual(loaded, [])

    def test_an_error_without_words_is_still_an_error(self):
        # str(e) of KeyError() or RuntimeError() is "": an error of "" would read as a load that worked
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            speaker, _ = self.speaker(Path(d), [])

            def load_onnx():
                raise RuntimeError()
            speaker._load_onnx = load_onnx
            loop = threading.Thread(target=speaker._synth_loop)
            loop.start()
            loop.join(5)
            self.assertTrue(speaker.ready.is_set())
            self.assertEqual(speaker.error, "RuntimeError")


class PrepareVoices(unittest.TestCase):
    """The bank made before the game is launched: never an error that ends the companion at «Играть», and
    «игра запустится, когда соберутся голоса рас» only when it is about to be made."""

    def prepare(self, stale, providers=("CUDAExecutionProvider", "CPUExecutionProvider")):
        from unittest import mock

        from bv import f5engine
        logged, made = [], []
        with mock.patch("bv.gamevoices.stale", stale), \
                mock.patch("onnxruntime.get_available_providers", lambda: list(providers)), \
                mock.patch.object(f5engine, "make_bank", lambda *a: made.append(1)):
            f5engine.prepare_voices({"f5_onnx_provider": "CUDAExecutionProvider"}, Path("."), logged.append)
        return logged, made

    def test_made_with_its_word(self):
        logged, made = self.prepare(lambda config, out: True)
        self.assertEqual((logged, made), (["игра запустится, когда соберутся голоса рас"], [1]))

    def test_nothing_to_make(self):
        self.assertEqual(self.prepare(lambda config, out: False), ([], []))

    def test_no_word_when_the_card_cannot_make_it(self):
        # the word was logged before prepare_voices found it would build nothing
        self.assertEqual(self.prepare(lambda config, out: True, ("CPUExecutionProvider",)), ([], []))

    def test_a_failing_look_at_the_bank_is_no_end(self):
        # stale() ran in main outside the guard: anything it raised ended the companion at «Играть» (exit 1,
        # a failed start for the update's rollback)
        def stale(config, out):
            raise TypeError("expected str, bytes or os.PathLike object, not int")
        logged, made = self.prepare(stale)
        self.assertEqual(made, [])
        self.assertEqual(len(logged), 1)
        self.assertTrue(logged[0].startswith("голоса рас из клиента: "), logged)


class OnCard(unittest.TestCase):
    """A session ONNX Runtime quietly put on the processor (DirectML without DirectX 12) is refused: the voice bank
    would take many minutes on Whisper there and the race voices would not run anyway."""

    def test_on_card(self):
        from bv.f5engine import on_card

        class Session:
            def __init__(self, *providers):
                self.providers = list(providers)

            def get_providers(self):
                return self.providers
        on_card(Session("DmlExecutionProvider", "CPUExecutionProvider"), "DmlExecutionProvider")
        on_card(Session("CUDAExecutionProvider", "CPUExecutionProvider"), "CUDAExecutionProvider")
        on_card(Session("CPUExecutionProvider"), "CPUExecutionProvider")          # asked for the processor: fine
        with self.assertRaises(RuntimeError) as told:
            on_card(Session("CPUExecutionProvider"), "DmlExecutionProvider")
        self.assertIn("DirectX 12", str(told.exception))
        # a provider of f5_onnx_provider outside PREFERRED was let run on the processor: F5 "ready" there
        on_card(Session("TensorrtExecutionProvider", "CPUExecutionProvider"), "TensorrtExecutionProvider")
        with self.assertRaises(RuntimeError):
            on_card(Session("CPUExecutionProvider"), "TensorrtExecutionProvider")

    def test_card_session(self):
        # F5 and Whisper (the voice bank) set their sessions up in one place: the same card, DirectML's needs
        from bv.f5engine import card_session
        options, providers = card_session("DmlExecutionProvider")
        self.assertFalse(options.enable_mem_pattern)
        self.assertEqual(providers, [("DmlExecutionProvider", {"device_id": 0, "performance_preference": "high_performance"}),
                                     "CPUExecutionProvider"])
        options, providers = card_session("CUDAExecutionProvider")
        self.assertTrue(options.enable_mem_pattern)
        self.assertEqual(providers, ["CUDAExecutionProvider", "CPUExecutionProvider"])
        self.assertEqual(card_session("CPUExecutionProvider")[1], ["CPUExecutionProvider"])
        # any other provider asked for gets it, the processor as the fallback (it got the processor alone)
        self.assertEqual(card_session("TensorrtExecutionProvider")[1], ["TensorrtExecutionProvider", "CPUExecutionProvider"])


class ModelsMissing(unittest.TestCase):
    """Which F5 failure a restart online can fix: a model missing from the cache, nothing else."""

    def test_models_missing_by_the_error(self):
        from huggingface_hub.errors import LocalEntryNotFoundError, OfflineModeIsEnabled

        from bv.f5engine import models_missing as missing_of
        self.assertTrue(missing_of(LocalEntryNotFoundError("not in the cache")))
        self.assertTrue(missing_of(OfflineModeIsEnabled("offline mode is enabled")))
        try:                                      # wrapped by another library: its cause counts
            try:
                raise LocalEntryNotFoundError("x")
            except LocalEntryNotFoundError as inner:
                raise OSError("RUAccent: could not load") from inner
        except OSError as outer:
            self.assertTrue(missing_of(outer))
        self.assertFalse(missing_of(RuntimeError("[TensorRT EP] failed to build the engine")))
        self.assertFalse(missing_of(FileNotFoundError("no game client")))   # a missing file, but not a model
        self.assertFalse(missing_of(None))


class FetchModels(unittest.TestCase):
    """F5's models: the word about a ~760 MB download only when they are not in the cache."""

    def test_the_download_said_only_when_it_happens(self):
        from unittest import mock

        from huggingface_hub.errors import LocalEntryNotFoundError

        from bv.f5engine import fetch_models
        calls, said = [], []

        def cached(repo, allow_patterns, local_files_only=False):
            calls.append(local_files_only)
            return "/cache/f5"

        def missing(repo, allow_patterns, local_files_only=False):
            calls.append(local_files_only)
            if local_files_only:
                raise LocalEntryNotFoundError("not in the cache")
            return "/cache/f5"
        with mock.patch.dict("os.environ", {"HF_HUB_OFFLINE": "0"}):
            with mock.patch("huggingface_hub.snapshot_download", cached):
                self.assertEqual(fetch_models({}, said.append), Path("/cache/f5"))
            self.assertEqual((calls, said), ([True], []))               # in the cache: no network, no word
            calls.clear()
            with mock.patch("huggingface_hub.snapshot_download", missing):
                fetch_models({}, said.append)
            self.assertEqual(calls, [True, False])                      # then downloaded
            self.assertEqual(len(said), 1)
            self.assertIn("в первый раз скачивается", said[0])


if __name__ == "__main__":
    unittest.main()
