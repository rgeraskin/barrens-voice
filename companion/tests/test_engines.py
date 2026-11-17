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

    def __init__(self, *a):
        self.ready = threading.Event()
        self.error = None
        self.stopped = False

    def start(self):
        self.error = FakeF5.fail
        if FakeF5.fail is not None:          # failed at once; else ready when the test says
            self.ready.set()

    def shutdown(self):
        self.stopped = True


class FakeSapi:
    def __init__(self):
        self.said = []

    def say(self, line):
        self.said.append(line.text)


from bv.engines import Engines  # noqa: E402

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

    def make(self):
        self.sapi = FakeSapi()
        return Engines({"engine": "f5", "spoken_notices": True}, lambda *a: None, Path("."), self.sapi, None)

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


class Accent:
    def accent(self, text):
        return text

    def load(self):
        pass


class F5SpeakerLoad(unittest.TestCase):
    """F5Speaker's own thread with ONNX Runtime and the game client faked (they are Windows only)."""

    def speaker(self, home, slots):
        from bv import f5engine
        from bv.assign import Assigner
        logged = []
        speaker = f5engine.F5Speaker({"max_queue": 8, "players": {}}, logged.append, home, Accent(),
                                     player=types.SimpleNamespace(generation=0))

        def load_onnx():
            speaker.assigner = Assigner(slots, home / "assignments.json", {})
        speaker._load_onnx = load_onnx
        return speaker, logged

    def test_an_empty_voice_bank_is_an_error(self):
        # a client without the Russian voice-over: the bank is made with no voices in it
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            speaker, _ = self.speaker(Path(d), [])
            loop = threading.Thread(target=speaker._synth_loop)
            loop.start()
            loop.join(5)
            self.assertFalse(loop.is_alive())
            self.assertTrue(speaker.ready.is_set())
            self.assertIn("русской озвучки", speaker.error)


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


if __name__ == "__main__":
    unittest.main()
