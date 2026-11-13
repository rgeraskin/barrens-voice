"""F5-TTS (Russian fine-tune) speaking chat lines in race voices from the game client, on the GPU.

One thread synthesises, another plays, so the next line is ready while one is being said.
"""
from __future__ import annotations

import contextlib
import io
import os
import re
import queue
import threading
import time
import wave
from pathlib import Path

from .assign import Assigner
from .audio import Player, wav
from . import gamevoices
from .intonation import shape
from .text import Accentor, numbers_to_words

SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")
GAP = 0.15   # seconds between sentence groups made separately


def sentence_groups(text: str) -> list[str]:
    """`text` cut into runs of statements and single questions, so each question can get its own
    intonation: "Привет. Кто идёт? Есть хил? Собираемся у входа." is four runs."""
    groups: list[str] = []
    last = None
    for sentence in SENTENCE_END.split(text.strip()):
        if not sentence:
            continue
        question = sentence.rstrip().endswith("?")
        if groups and not question and last is False:
            groups[-1] += " " + sentence
        else:
            groups.append(sentence)
        last = question
    return groups or [text]

MODEL_REPO = "Misha24-10/F5-TTS_RUSSIAN"
MODEL_FILE = "F5TTS_v1_Base_v2/model_last_inference.safetensors"
VOCAB_FILE = "F5TTS_v1_Base/vocab.txt"


TARGET_RMS = 0.08     # about -22 dBFS: every voice about as loud as the others
PEAK = 0.95


def tidy(samples, rate: int, gain_db: float = 0.0):
    """Speech with the silence before it cut (keeping 50 ms) and its loudness evened out: to
    TARGET_RMS, `gain_db` louder or quieter (a yell, a whisper), never over PEAK. One gain for the
    whole line, so the intonation inside it is kept."""
    import numpy as np

    samples = np.asarray(samples, dtype="float32")
    if not len(samples):
        return samples
    peak = float(np.max(np.abs(samples))) or 1.0
    loud = np.flatnonzero(np.abs(samples) > peak * 0.03)  # about -30 dB under the peak
    if len(loud):
        samples = samples[max(0, loud[0] - rate // 20):]  # keep 50 ms before the first sound
    rms = float(np.sqrt(np.mean(samples ** 2))) or 1e-6
    gain = TARGET_RMS * 10 ** (gain_db / 20) / rms
    peak = float(np.max(np.abs(samples))) or 1e-6
    gain = min(gain, PEAK / peak)
    return samples * gain


KNEE = 0.8   # peaks above this are bent smoothly toward full scale instead of clipped


def limit(samples):
    """Peaks over KNEE eased toward 1.0 (tanh) instead of cut off: a line played louder than 100 %
    (the addon's volume goes to 200 %) stays clean; below KNEE nothing changes."""
    import numpy as np

    a = np.abs(samples)
    over = a > KNEE
    if not over.any():
        return samples
    out = np.array(samples, dtype="float32")
    out[over] = np.sign(out[over]) * (KNEE + (1 - KNEE) * np.tanh((a[over] - KNEE) / (1 - KNEE)))
    return out


def wav_bytes(samples, rate: int, volume: float, gain_db: float = 0.0) -> bytes:
    import numpy as np

    samples = limit(tidy(samples, rate, gain_db) * volume)
    return wav((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes(), rate)


def make_bank(config: dict, home: Path, log) -> list:
    """The voice bank (gamevoices): as it is, or made again from the game client with Whisper
    loaded for it and freed from the GPU afterwards."""
    out = home / "voices"
    checker = None
    if gamevoices.stale(config, out):
        from .refcheck import Checker
        checker = Checker(log)
        if not checker.load():
            checker = None
    try:
        return gamevoices.build(config, out, log, checker)
    finally:
        if checker is not None:
            checker.pipe = None
            import gc
            import torch
            gc.collect()
            torch.cuda.empty_cache()


def prepare_voices(config: dict, home: Path, log) -> None:
    """Before the game starts: (re)make the voice bank if the game was updated since, so its files
    are read while nothing (Battle.net patching, the game) is busy with them. Quiet when the bank
    is up to date or F5 cannot run here (the F5 engine reports that when it is asked for)."""
    try:
        if not gamevoices.stale(config, home / "voices"):
            return
        import torch
        if not torch.cuda.is_available():
            return
        make_bank(config, home, log)
    except ImportError:
        return
    except Exception as e:  # noqa: BLE001 - tried again when the F5 engine loads
        log(f"голоса рас из клиента: {e}")


CUT_TAIL = 0.06   # seconds of quiet after the last sound below which the ending did not fit


def line_seconds(pace: float, target_pace: float, text_bytes: int, rate: int, character: str,
                 config: dict) -> float:
    """Seconds of speech for a line (F5 takes its tempo from the length it is given).

    `pace` is the voice's own (its reference's seconds per byte of text). The game's recordings
    differ up to fourfold: a hurried error message of a character, a solemn NPC greeting. A voice
    slower than `target_pace` - the faster quarter of the bank (`voice_pace_quantile`), near the
    characters' own voices: the bank's median is a typical NPC, itself unhurried - is drawn toward
    it by `voice_pace_blend` (geometric; 0 keeps the voice's own, 1 brings it all the way), by at
    most `voice_pace_limit` times; faster voices stay as they are. Each character then gets a
    tempo of their own, within ±`character_tempo` (stable: from the name), so two characters with
    the same voice still sound like two people. The addon's speed slider (`rate`) goes on top, and
    `f5_margin`/`f5_tail` keep the last syllables from being squeezed."""
    import zlib

    target = pace
    if target_pace and pace > target_pace:
        blend = config.get("voice_pace_blend", 0.85)
        target = max(pace / config.get("voice_pace_limit", 1.8), pace ** (1 - blend) * target_pace ** blend)
    spread = config.get("character_tempo", 0.08)
    if character and spread:
        unit = (zlib.crc32(character.lower().encode("utf-8")) % 1001) / 1000      # 0..1, stable per name
        target *= 1 + spread * (2 * unit - 1)
    line = target * text_bytes / (rate / 100)
    return line * config["f5_margin"] + config["f5_tail"]


def silence_after(samples, rate: int) -> float:
    """Seconds after the last sound (frames louder than a tenth of the loudest)."""
    import numpy as np

    x = np.asarray(samples, dtype="float32")
    n = int(rate * 0.01)
    k = len(x) // n
    if k == 0:
        return 0.0
    rms = np.sqrt(np.mean(x[:k * n].reshape(k, n) ** 2, axis=1))
    loud = np.flatnonzero(rms > rms.max() * 0.1)
    return (k - 1 - loud[-1]) * 0.01 if len(loud) else 0.0


class F5Speaker:
    def __init__(self, config: dict, log, home: Path, accentor: Accentor | None = None,
                 player: Player | None = None):
        self.config, self.log, self.home = config, log, home
        self.player = player
        self.lines: queue.Queue = queue.Queue()
        self.working = False         # a line taken from the queue and not yet handed to the player
        self.ready = threading.Event()
        self.error: str | None = None
        self.accentor = accentor or Accentor(log, config.get("ruaccent", True))
        self.assigner: Assigner | None = None
        self.tts = None
        self.ref_text: dict[str, str] = {}
        self.target_pace = 0.0

    # --- setup (on the synth thread) --------------------------------------------------------

    def _load(self) -> None:
        import soundfile as sf
        import torch
        import torchaudio

        if not torch.cuda.is_available():
            raise RuntimeError("нет видеокарты NVIDIA с CUDA")

        def load_audio(path, *a, **k):   # torchaudio 2.11 decodes through torchcodec (FFmpeg DLLs)
            data, rate = sf.read(str(path), dtype="float32", always_2d=True)
            return torch.from_numpy(data.T.copy()), rate
        torchaudio.load = load_audio

        slots = make_bank(self.config, self.home, self.log)
        self.assigner = Assigner(slots, self.home / "assignments.json", self.config["players"])

        self.log("загружаю RUAccent ...")
        self.accentor.load()
        self.log("загружаю F5-TTS ...")
        from huggingface_hub import hf_hub_download
        from f5_tts.api import F5TTS

        # F5 prints "Download Vocos from huggingface" every time, though it takes it from the cache
        with contextlib.redirect_stdout(io.StringIO()):
            self.tts = F5TTS(model="F5TTS_v1_Base", ckpt_file=hf_hub_download(MODEL_REPO, MODEL_FILE),
                             vocab_file=hf_hub_download(MODEL_REPO, VOCAB_FILE), device="cuda")
        offline = os.environ.get("HF_HUB_OFFLINE") == "1"
        self.log("модели F5 и Vocos: " + ("из кэша, без сети" if offline else "из кэша Hugging Face (с проверкой обновлений)"))
        self.ref_text = {s.id: self.accentor.accent(s.text) for s in slots}
        self.ref_seconds = {s.id: sf.info(s.path).duration for s in slots}
        paces = sorted(s.speech / max(1, len(s.text.encode("utf-8"))) for s in slots if s.shift == 0 and s.speech)
        quantile = self.config.get("voice_pace_quantile", 0.25)
        self.target_pace = paces[min(len(paces) - 1, int(len(paces) * quantile))] if paces else 0.0
        first = next(s for s in slots if s.race)
        self._synth(first, "Проверка.", 100)   # warm-up: the first call is slow
        self.log(f"F5-TTS готов на {torch.cuda.get_device_name(0)}")

    def reference(self, slot, text: str):
        """(clip, its text, its seconds)."""
        return slot.path, self.ref_text[slot.id], self.ref_seconds[slot.id]

    def duration(self, slot, text: str, rate: int, character: str = "") -> float:
        """Total seconds (reference + line) to give F5 - which fits the speech into exactly that
        length, so this sets the voice's tempo: see `line_seconds`."""
        _, ref_text, ref = self.reference(slot, text)
        pace = (slot.speech or ref) / max(1, len(ref_text.encode("utf-8")))
        return ref + line_seconds(pace, self.target_pace, len(text.encode("utf-8")), rate, character,
                                  self.config)

    def _synth(self, slot, text: str, rate: int, character: str = ""):
        """The line in `slot`'s voice. When the speech runs to the very end of the length given (the
        last syllable did not fit: F5 is random, and one line in ten did that), it is made once
        more with a quarter more length - that brought it to one in sixty."""
        ref_file, ref_text, ref = self.reference(slot, text)
        total = self.duration(slot, text, rate, character)
        for attempt in range(2):
            with contextlib.redirect_stdout(io.StringIO()):   # F5 prints ref_text/gen_text for each call
                wav, sr, _ = self.tts.infer(ref_file=ref_file, ref_text=ref_text, gen_text=text,
                                            nfe_step=self.config["nfe_step"], speed=rate / 100,
                                            fix_duration=total, show_info=lambda *a: None, progress=None)
            if attempt or silence_after(wav, sr) >= CUT_TAIL:
                break
            total = ref + (total - ref) * 1.25
        return wav, sr

    # --- threads ----------------------------------------------------------------------------

    def start(self) -> None:
        if self.player is None:
            self.player = Player(self.config["max_queue"])
            self.player.start()
        threading.Thread(target=self._synth_loop, daemon=True, name="f5-synth").start()

    def _synth_loop(self) -> None:
        try:
            self._load()
        except Exception as e:  # noqa: BLE001 - reported, the caller falls back to SAPI
            self.error = str(e)
            self.ready.set()
            return
        self.ready.set()
        while True:
            self.working = False
            line = self.lines.get()
            self.working = True
            if line is None:                 # shutdown: free the model and the GPU memory
                self.tts = None
                import gc
                import torch
                gc.collect()
                torch.cuda.empty_cache()
                return
            generation = self.player.generation   # a stop while this is being made drops it
            slot = self.assigner.slot_for(line.sender, line.race, line.sex)
            if slot is None:
                continue
            # numbers first: RUAccent then stresses the number words too ("шестн+адцать"; F5 left
            # to itself put it on the first syllable in some voices)
            text = self.accentor.accent(numbers_to_words(line.text))
            if text[-1:].isalnum() or text[-1:] == "+":
                text += "."
            if self.config.get("log_details") and text != line.text:
                groups = sentence_groups(text)
                self.log(f"    к синтезу: {text}" + (f"  ({len(groups)} части)" if len(groups) > 1 else ""))
            started = time.perf_counter()
            try:
                import numpy as np
                pieces, sr = [], 24000
                for group in sentence_groups(text):
                    piece, sr = self._synth(slot, group, line.rate, line.sender)
                    piece = shape(piece, sr, group, self.config.get("question_intonation"))
                    if pieces:
                        pieces.append(np.zeros(int(sr * GAP), dtype=piece.dtype))
                    pieces.append(piece)
                    if generation != self.player.generation:
                        break                       # stopped meanwhile: no need to finish
                wav = np.concatenate(pieces)
            except Exception as e:  # noqa: BLE001 - one bad line must not stop the reader
                self.log(f"F5-TTS: {e}")
                continue
            if self.config.get("debug"):
                self.log(f"  синтез {time.perf_counter() - started:.2f} с, {len(wav) / sr:.1f} с звука")
            gain = self.config["kind_gain_db"].get(line.kind, 0)
            self.player.play(wav_bytes(wav, sr, line.gain(self.config), gain), generation)

    # --- the reader's side ------------------------------------------------------------------

    def describe(self, line) -> str:
        if self.assigner is None:
            return "-"
        slot = self.assigner.slot_for(line.sender, line.race, line.sex)
        return slot.id if slot else "-"

    def clear(self) -> None:
        while not self.lines.empty():
            try:
                self.lines.get_nowait()
            except queue.Empty:
                break

    def shutdown(self) -> None:
        """Stop after the line being made; the model is freed on the synth thread."""
        if self.assigner is not None:
            self.assigner.flush()
        while not self.lines.empty():
            try:
                self.lines.get_nowait()
            except queue.Empty:
                break
        self.lines.put(None)

    def say(self, line) -> None:
        from .audio import queue_line
        queue_line(self.lines, line, self.config["max_queue"], self.log)


def selftest(config: dict, log, home: Path) -> int:
    """Build the voice bank and synthesise a line for a few characters into home/f5test, timed."""
    import soundfile as sf
    from .protocol import Line

    speaker = F5Speaker(config, log, home)
    speaker._load()
    out = home / "f5test"
    out.mkdir(exist_ok=True)
    cast = [("Громмаш", "Orc", "2"), ("Гаррош", "Orc", "2"), ("Дрекша", "Orc", "3"), ("Джайна", "Human", "3"),
            ("Брэнн", "Dwarf", "2"), ("Тиранда", "NightElf", "3"), ("Вол'джин", "Troll", "2"), ("Сильвана", "Scourge", "3")]
    for name, race, sex in cast:
        line = Line("test", name, race, sex, "", "", "Нужен дд в Мёртвые копи, продам сумки за 5000.")
        slot = speaker.assigner.slot_for(name, race, sex)
        text = speaker.accentor.accent(numbers_to_words(line.text))
        started = time.perf_counter()
        wav, sr = speaker._synth(slot, text, 100, name)
        took = time.perf_counter() - started
        sf.write(str(out / f"{race}_{name}.wav"), wav, sr)
        log(f"{name:9s} {race:8s} -> {slot.id:22s} {took:.2f} с на {len(wav) / sr:.1f} с звука")
    import ctypes
    import torch

    class Counters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    c = Counters()
    c.cb = ctypes.sizeof(c)
    kernel32.K32GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(c), c.cb)
    log(f"память: {c.WorkingSetSize / 2**30:.2f} ГБ (пик {c.PeakWorkingSetSize / 2**30:.2f}), "
        f"видеопамять: {torch.cuda.max_memory_reserved() / 2**30:.2f} ГБ")
    log(f"файлы: {out}")
    return 0
