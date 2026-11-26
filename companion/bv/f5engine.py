"""F5-TTS (Russian fine-tune) speaking chat lines in race voices from the game client, on the GPU.

One thread synthesises, another plays, so the next line is ready while one is being said. F5 runs
through ONNX Runtime (bv/f5onnx.py): on CUDA with an NVIDIA card, on DirectML with any other DirectX 12
card (it holds the GPU for a whole step, so the game's frames wait: DEVELOPMENT.md). Up to 0.3.0 it ran
through torch on CUDA (gigabytes to install); that code was removed in the commit "F5: torch
removed, ONNX Runtime only" - `git revert` it to bring torch back (DEVELOPMENT.md).
"""
from __future__ import annotations

import os
import re
import queue
import threading
import time
from pathlib import Path

from .assign import Assigner
from .audio import KNEE, TAIL, Player, drain, limit, wav  # noqa: F401 - KNEE and limit: tests and tools take them here
from . import gamevoices
from .intonation import shape
from .text import Accentor, numbers_to_words

SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")
GAP = 0.15   # seconds between sentence groups made separately


FIRST_WORDS = 4   # a first sentence made on its own only with this many words on each side (first_and_rest)
PART_SECONDS = 15.0   # the longest speech one F5 call makes (config.json `f5_part_seconds`): see within()
# where a part too long is cut, best first: sentence ends, then clause marks (a comma, «;», «:», a dash between spaces,
# the dash kept with the words before it), then any space
CUTS = (SENTENCE_END, re.compile(r"(?<=[,;:])\s+|(?<=\s[—–-])\s+"), re.compile(r"\s+"))
# words a piece cut between words should not end on - they lean on the word after them («…и не | ливает»); not «же»,
# «бы», «ли» - they lean on the word before («сказал бы»)
LEANING = frozenset("и а но или да не ни в во на с со к ко по за от до из у о об обо при для без под над про через что "
                    "как чтобы если то and or but the a an to of in on at for with from not".split())


def within(text: str, seconds, limit: float) -> list[str]:
    """`text` cut into pieces of at most `limit` seconds of speech each (`seconds(piece)`, the length F5 would be
    given), each its own F5 call. F5 makes a line in one go, its reference voice included, and was taught on clips of
    up to 30 seconds (upstream cuts so that reference and piece are 22 s, utils_infer.chunk_text); the length is
    capped too (Metadata's max_signal_length, 4096 frames - about 44 seconds with the reference). Cut where a speaker
    pauses anyway - at sentence ends, else at commas and dashes -, pieces joined back while they fit, so «… & more.
    PST!» keeps its «PST!» with the words before it; a short sentence before a long one goes with its head
    («Внимание! Сегодня в восемь…»), not alone; a clause still too long is cut between words into runs of about
    equal length, not filled up to leave a word or two; a piece without a letter (a lone dash) goes with the one
    before it, a dash ending a piece (not the last) becomes a comma - a pause F5 knows from its training, as upstream's
    pieces end."""
    pieces: list[str] = []
    for piece in _cut(text.strip(), seconds, limit, 0):
        if pieces and not any(ch.isalnum() for ch in piece):
            pieces[-1] = f"{pieces[-1]} {piece}"
        elif pieces and not any(ch.isalnum() for ch in pieces[-1]):
            pieces[-1] = f"{pieces[-1]} {piece}"
        else:
            pieces.append(piece)
    return [re.sub(r"[,;:]*\s+[—–-]$", ",", piece) if index < len(pieces) - 1 else piece
            for index, piece in enumerate(pieces)]


def _cut(text: str, seconds, limit: float, level: int) -> list[str]:
    if seconds(text) <= limit or level == len(CUTS):
        return [text]
    units = [unit for unit in CUTS[level].split(text) if unit]
    if len(units) == 1:
        return _cut(text, seconds, limit, level + 1)
    if level == len(CUTS) - 1:
        return _even(units, seconds, limit)
    pieces: list[str] = []
    for unit in units:
        if pieces and seconds(f"{pieces[-1]} {unit}") <= limit:
            pieces[-1] = f"{pieces[-1]} {unit}"
        elif level == 0 and pieces and len(pieces[-1].split()) < FIRST_WORDS and len(
                joined := _cut(f"{pieces[-1]} {unit}", seconds, limit, level + 1)) <= len(
                _cut(unit, seconds, limit, level + 1)):     # a short sentence with the next one's head: a call saved
            pieces[-1:] = joined
        else:
            pieces.extend(_cut(unit, seconds, limit, level + 1))
    return pieces


def _even(words: list[str], seconds, limit: float) -> list[str]:
    """`words` in the fewest runs of about equal length (by bytes, as the estimate counts) that each fit, a run that
    would end on a LEANING word («и», «не», «в», RUAccent's «чт+обы» too) ending a word or two sooner when both runs
    still fit; with a word alone over the limit (no count fits: «ахахаха…»), runs filled while they fit, that word on
    its own."""
    sizes = [len(word.encode("utf-8")) + 1 for word in words]
    total = sum(sizes)
    for runs in range(2, len(words) + 1):
        bounds, done = [0], 0
        for index, size in enumerate(sizes[:-1], 1):
            done += size
            if done >= total * len(bounds) / runs:
                bounds.append(index)
        bounds.append(len(words))
        for at in range(1, len(bounds) - 1):
            bound = bounds[at]
            while (bound - 1 > bounds[at - 1] and words[bound - 1].lower().replace("+", "").strip(",.;:!?…") in LEANING
                   and seconds(" ".join(words[bound - 1:bounds[at + 1]])) <= limit):
                bound -= 1
            bounds[at] = bound
        pieces = [" ".join(words[a:b]) for a, b in zip(bounds, bounds[1:]) if a < b]
        if all(seconds(piece) <= limit for piece in pieces):
            return pieces
    pieces = [words[0]]
    for word in words[1:]:
        if seconds(f"{pieces[-1]} {word}") <= limit:
            pieces[-1] = f"{pieces[-1]} {word}"
        else:
            pieces.append(word)
    return pieces


def first_and_rest(text: str) -> list[str]:
    """`text` as its first part and the rest (config.json `f5_first_sentence`: the first plays while the rest is made),
    cut where it pays: where the line's groups part anyway (a question after statements, sentence_groups - no extra F5
    call), else after its first sentence when it and the rest have FIRST_WORDS words each. Each F5 call carries the
    reference's seconds, so «привет. го в данж» (the addon's full stop for a smiley) or «ну. не знаю» cut in two
    would cost nearly twice the work for a word's head start; such a line stays whole."""
    if not any(ch.isalnum() for ch in text):
        return []                                   # nothing to say (empty, a lone bracket): no F5 call
    groups = sentence_groups(text)
    if len(groups) > 1:
        return [groups[0], " ".join(groups[1:])]
    sentences = [part for part in SENTENCE_END.split(text.strip()) if part]
    for end in range(1, len(sentences)):            # the first sentence end with FIRST_WORDS on each side
        first, rest = " ".join(sentences[:end]), " ".join(sentences[end:])
        if len(first.split()) >= FIRST_WORDS and len(rest.split()) >= FIRST_WORDS:
            return [first, rest]
    return [text]


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

MODEL_REPO = "Misha24-10/F5-TTS_RUSSIAN"   # the vocabulary; the model itself is our ONNX export of it
VOCAB_FILE = "F5TTS_v1_Base/vocab.txt"
# the video card, best first: CUDA (NVIDIA; onnxruntime-gpu) leaves the game alone - DirectML (any DirectX 12
# card; onnxruntime-directml) holds the card for a whole denoising step, and the game's frames wait (DEVELOPMENT.md)
PREFERRED = ("CUDAExecutionProvider", "DmlExecutionProvider")
# our ONNX export of that model (10 steps; Hugging Face, CC BY-NC 4.0 as the model), downloaded into
# the model cache at the first start unless the graphs are in models/f5-onnx or `f5_onnx_dir`
ONNX_REPO = "rgeraskin/barrens-voice-f5-onnx"


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


def wav_bytes(samples, rate: int, volume: float, gain_db: float = 0.0, tail: float = TAIL) -> bytes:
    import numpy as np

    samples = limit(tidy(samples, rate, gain_db) * volume)
    return wav((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes(), rate, tail=tail)


def provider(config: dict, available: list[str] | None = None) -> str:
    """ONNX Runtime's execution provider for F5 and Whisper: `f5_onnx_provider`, else the first of
    PREFERRED this ONNX Runtime has (CUDA in onnxruntime-gpu, DirectML in onnxruntime-directml)."""
    if config.get("f5_onnx_provider"):
        return config["f5_onnx_provider"]
    if available is None:
        try:
            import onnxruntime
            available = onnxruntime.get_available_providers()
        except ImportError:
            available = []
    return next((p for p in PREFERRED if p in available), "CPUExecutionProvider")


def on_card(session, engine: str) -> None:
    """A session asked for the video card runs there: ONNX Runtime falls back to the processor quietly when
    the card cannot (DirectML without DirectX 12), and the race voices would then take tens of seconds a
    line - and the voice bank, built first, many minutes for nothing. Raises then: for any provider asked for
    other than the processor itself (f5_onnx_provider "TensorrtExecutionProvider" too)."""
    used = session.get_providers()[0] if session.get_providers() else "?"
    if engine != "CPUExecutionProvider" and used != engine:
        raise RuntimeError(f"{engine} не запустился на этой видеокарте (ONNX Runtime перешёл на {used}): "
                           "нужна NVIDIA (CUDA) или видеокарта с DirectX 12")


def card_session(engine: str):
    """(SessionOptions, providers) for a graph on the video card, F5's and Whisper's alike: DirectML's
    own requirements (no memory pattern, one node at a time) and its fastest card; the processor last,
    as ONNX Runtime's fallback (`on_card` refuses a session that fell back); the processor alone for the
    processor."""
    import onnxruntime as ort
    options = ort.SessionOptions()
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    if engine == "DmlExecutionProvider":
        options.enable_mem_pattern = False
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        return options, [(engine, {"device_id": 0, "performance_preference": "high_performance"}),
                         "CPUExecutionProvider"]
    if engine == "CPUExecutionProvider":
        return options, [engine]
    return options, [engine, "CPUExecutionProvider"]


def preload(engine: str) -> None:
    """CUDA and cuDNN from their pip packages (onnxruntime-gpu[cuda,cudnn]) before a CUDA session."""
    if engine == "CUDAExecutionProvider":
        import onnxruntime
        if hasattr(onnxruntime, "preload_dlls"):
            onnxruntime.preload_dlls()


def model_dir(config: dict, home: Path) -> Path | None:
    """The folder of F5's ONNX graphs on this computer: `f5_onnx_dir`, else models/f5-onnx next to
    the program when they are there; None means: from Hugging Face (`fetch_models`)."""
    if config.get("f5_onnx_dir"):
        return Path(config["f5_onnx_dir"])
    local = home / "models" / "f5-onnx"
    return local if (local / "F5_Metadata.onnx").exists() else None


def fetch_models(config: dict, log) -> Path:
    """F5's ONNX graphs from Hugging Face into the model cache (~760 MB once; then from the cache,
    offline like the other models). The cache is asked first, without the network: the word about the download
    only when there is one (a snapshot missing or incomplete: LocalEntryNotFoundError, IncompleteSnapshotError)."""
    from huggingface_hub import snapshot_download
    from huggingface_hub.errors import LocalEntryNotFoundError
    repo = config.get("f5_onnx_repo") or ONNX_REPO
    try:
        return Path(snapshot_download(repo, allow_patterns=["*.onnx"], local_files_only=True))
    except LocalEntryNotFoundError:
        pass
    if os.environ.get("HF_HUB_OFFLINE") != "1":
        log(f"модели F5 (ONNX): {repo} — в первый раз скачивается ~760 МБ ...")
    return Path(snapshot_download(repo, allow_patterns=["*.onnx"]))


def models_missing(error: BaseException | None) -> bool:
    """Was it a model missing from the Hugging Face cache while offline (`offline_models`): a file not
    there, or the hub asked in offline mode - here or as the cause of another library's error. Only then
    a restart online helps; a video card's failure (TensorRT not starting, no DirectX 12), a client without
    the Russian voice-over and the like are not fixed by the network."""
    from huggingface_hub.errors import LocalEntryNotFoundError, OfflineModeIsEnabled
    seen = set()
    while error is not None and id(error) not in seen:
        if isinstance(error, (LocalEntryNotFoundError, OfflineModeIsEnabled)):
            return True
        seen.add(id(error))
        error = error.__cause__ or error.__context__
    return False


def gpu_name() -> str:
    """The video card DirectML runs on (its device 0: the adapter the desktop is on), for people to
    read; "" if Windows does not say."""
    try:
        import win32api
        return str(win32api.EnumDisplayDevices(None, 0).DeviceString).strip()
    except Exception:  # noqa: BLE001 - only a label
        return ""


def make_bank(config: dict, home: Path, log) -> list:
    """The voice bank (gamevoices): as it is, or made again from the game client with Whisper
    loaded for it and freed from the GPU afterwards."""
    out = gamevoices.bank_dir(config, home)
    checker = None
    if gamevoices.stale(config, out):
        from . import state
        state.report(voices="bank")
        from .whisper_onnx import OnnxChecker
        preload(provider(config))
        checker = OnnxChecker(log, provider(config))
        if not checker.load():
            checker = None
    try:
        return gamevoices.build(config, out, log, checker)
    finally:
        if checker is not None:
            import gc
            checker.encoder = checker.decoder = None
            gc.collect()


def prepare_voices(config: dict, home: Path, log) -> None:
    """Before the game starts: (re)make the voice bank if the game was updated since, so its files
    are read while nothing (Battle.net patching, the game) is busy with them. Quiet when the bank
    is up to date or F5 cannot run here (the F5 engine reports that when it is asked for). Never raises:
    whatever goes wrong here is tried again when the F5 engine loads, and the game starts anyway."""
    try:
        if not gamevoices.stale(config, gamevoices.bank_dir(config, home)):
            return
        import onnxruntime
        if provider(config) not in onnxruntime.get_available_providers() or provider(config) == "CPUExecutionProvider":
            return
        log("игра запустится, когда соберутся голоса рас")
        make_bank(config, home, log)
    except ImportError:
        return
    except Exception as e:  # noqa: BLE001 - tried again when the F5 engine loads
        log(f"голоса рас из клиента: {e}")


CUT_TAIL = 0.06   # seconds of quiet after the last sound below which the ending may not have fit


def ending_heard(expected: str, heard: str) -> bool:
    """Whether Whisper heard the line's last word in a take: the judge of a cut ending.

    Whole: the last word as written; or Whisper's run-together of the last two («в ульдаман» ->
    «вульдаман»); or the word with letters added at its end («копи» -> «копии»: a cut takes sounds
    away, it does not add them); a last word in digits (Whisper writes numbers so, the line has
    them in words). Whisper also writes a word as it hears it - «рейд» as «рейт», an unknown
    «хильте» as «хильти», three words as one: then the ending counts when the letters before it are
    not fewer (a cut word is shorter: «всем по-» for «всем пока») and the last word's length of
    letters at the end is alike."""
    from difflib import SequenceMatcher

    from .refcheck import words

    want, got = words(expected), words(heard)
    if not want:
        return True
    if not got:
        return False
    last = got[-1]
    if any(ch.isdigit() for ch in last):
        return True
    if last.startswith(want[-1]) or last == "".join(want[-2:]):
        return True
    expected, said, k = "".join(want), "".join(got), len(want[-1])
    return len(said) >= len(expected) - 1 and SequenceMatcher(None, expected[-k:], said[-k:]).ratio() >= 0.6


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
        self.models_missing = False   # the error was a model not in the cache while offline (models_missing)
        self.accentor = accentor or Accentor(log, config.get("ruaccent", True))
        self.assigner: Assigner | None = None
        self.onnx = None             # F5Onnx, once loaded
        self.checker = None          # Whisper (whisper_onnx.OnnxChecker), the judge of cut endings
        self.device = self.card = self.provider = ""
        self.ref_text: dict[str, str] = {}
        self.target_pace = 0.0

    # --- setup (on the synth thread) --------------------------------------------------------

    def _load(self) -> None:
        self._load_onnx()
        import soundfile as sf
        slots = self.assigner.slots
        first = next(s for s in slots if s.race)     # _load_onnx refused a bank without race voices
        self.ref_text = {s.id: self.accentor.accent(s.text) for s in slots}
        self.ref_seconds = {s.id: sf.info(s.path).duration for s in slots}
        paces = sorted(self.pace(s) for s in slots if s.shift == 0 and s.speech)
        quantile = self.config.get("voice_pace_quantile", 0.25)
        self.target_pace = paces[min(len(paces) - 1, int(len(paces) * quantile))] if paces else 0.0
        self._synth(first, "Проверка.", 100, say=False)   # warm-up: the first call is slow; its ending not logged
        self.log(f"F5-TTS готов на {self.device}")

    def _load_onnx(self) -> None:
        """F5 through ONNX Runtime; the models from `model_dir`."""
        import onnxruntime

        engine = provider(self.config)
        preload(engine)
        if engine not in onnxruntime.get_available_providers() or engine == "CPUExecutionProvider":
            raise RuntimeError(f"ONNX Runtime без видеокарты ({engine}): нужна NVIDIA (CUDA) или DirectX 12")
        models = model_dir(self.config, self.home) or fetch_models(self.config, self.log)
        if not (models / "F5_Metadata.onnx").exists():
            raise RuntimeError(f"нет моделей F5 в ONNX: {models} (f5_onnx_dir в config.json)")
        slots = make_bank(self.config, self.home, self.log)
        if not any(s.race for s in slots):   # before the models: a retry (RETRY_AFTER) loads nothing for nothing
            # a client without the Russian voice-over (or before it is downloaded)
            raise RuntimeError("в клиенте игры нет русской озвучки: голоса рас не из чего собрать")
        self.assigner = Assigner(slots, self.home / "assignments.json", self.config["players"])
        self.log("загружаю RUAccent ...")
        self.accentor.load()
        self.log("загружаю F5-TTS (ONNX) ...")
        from huggingface_hub import hf_hub_download

        from .f5onnx import F5Onnx
        self.onnx = F5Onnx(models, Path(hf_hub_download(MODEL_REPO, VOCAB_FILE)), engine, self.log,
                           self.fewer_steps(models))
        self.onnx.load()
        if self.config.get("f5_end_check") == "whisper":
            from .whisper_onnx import OnnxChecker
            checker = OnnxChecker(self.log, engine)
            self.checker = checker if checker.load() else None
        self.ref_audio: dict[str, object] = {}
        self.card = (gpu_name() if engine in ("DmlExecutionProvider", "CUDAExecutionProvider") else "") or engine
        self.provider = engine
        self.device = f"{self.card} (ONNX Runtime, {self.onnx.steps} шагов)"

    def fewer_steps(self, models: Path):
        """config.json `f5_steps` (the launcher's «Голоса рас: Качество · Баланс · Скорость»): the Transformer rewritten for that
        many steps (f5_schedule: made once into the cache's f5-steps, then reused; another number's file there is
        removed - 660 MB each) and the number; None for the shipped 10 (the folder removed) - and for a number or a
        model f5_schedule does not know, or a rewrite that fails at all (memory, a broken file), said in the log."""
        import shutil

        from .paths import CACHE_DIR
        folder = CACHE_DIR / "f5-steps"
        steps = self.config.get("f5_steps", 10)
        if steps == 10:
            shutil.rmtree(folder, ignore_errors=True)
            return None
        from .f5_schedule import STEPS, transformer
        if steps not in STEPS:
            self.log(f"не удалось взять f5_steps = {steps} из config.json: бывает 10, 8, 6, 5 или 4 — беру 10")
            return None
        from .f5onnx import transformer_file
        try:
            made = transformer(transformer_file(models), folder, steps)
        except Exception as e:  # noqa: BLE001 - the shipped 10 steps rather than no race voices
            self.log(f"не удалось подготовить F5 в {steps} шагов: {e} — беру 10")
            return None
        for other in folder.glob("F5_Transformer-*"):
            if not other.name.startswith(made.name):
                try:
                    other.unlink(missing_ok=True)
                except OSError:                     # held a moment (an antivirus, the indexer): the next start
                    pass
        return made, steps

    def pace(self, slot) -> float:
        """The voice's seconds of speech per byte of its reference's text as F5 gets it - stressed, as
        the lines are counted (`duration`): the bank's target pace and each voice's own in one unit."""
        return (slot.speech or self.ref_seconds[slot.id]) / max(1, len(self.ref_text[slot.id].encode("utf-8")))

    def duration(self, slot, text: str, rate: int, character: str = "") -> float:
        """Total seconds (reference + line) to give F5 - which fits the speech into exactly that
        length, so this sets the voice's tempo: see `line_seconds`."""
        ref = self.ref_seconds[slot.id]
        return ref + line_seconds(self.pace(slot), self.target_pace, len(text.encode("utf-8")), rate, character,
                                  self.config)

    def _synth(self, slot, text: str, rate: int, character: str = "", say: bool = True):
        """The line in `slot`'s voice. F5 fits the speech into the length it is given, and sometimes
        the last syllable does not fit. A take whose speech runs to its very end (`silence_after`
        under CUT_TAIL: one line in eight, most of them whole) is made once more with a quarter
        more length: always (`f5_end_check` "silence", the default), or only when Whisper does not
        hear the last word ("whisper": a second saved on such lines for 1.5 GB of video memory)."""
        ref_file, ref_text, ref = slot.path, self.ref_text[slot.id], self.ref_seconds[slot.id]
        total = self.duration(slot, text, rate, character)
        if ref_file not in self.ref_audio:
            import soundfile as sf
            from .whisper_onnx import resample
            data, sr_in = sf.read(ref_file, dtype="float32", always_2d=True)
            self.ref_audio[ref_file] = resample(data.mean(axis=1), sr_in, self.onnx.in_rate)
        for attempt in range(2):
            wav, sr = self.onnx.synth(self.ref_audio[ref_file], ref_text, text, total)
            if attempt or silence_after(wav, sr) >= CUT_TAIL or self._whole(wav, sr, text, say):
                break
            total = ref + (total - ref) * 1.25
        return wav, sr

    def spoken(self, text: str) -> str:
        """A line's text (the chat's pipeline done: __main__.speech_text) as F5 gets it: numbers to words first, so that
        RUAccent stresses the number words too ("шестн+адцать"; F5 left to itself put it on the first syllable in some
        voices), then the stresses; a full stop at its end."""
        text = self.accentor.accent(numbers_to_words(text))
        if text[-1:].isalnum() or text[-1:] == "+":
            text += "."
        return text

    def render(self, slot, text: str, rate: int = 100, character: str = "", gain_db: float = 0.0,
               stopped=lambda: False):
        """`text` (spoken()) in `slot`'s voice as the game plays it, part by part as each is made - the program's lines
        and the voice lab's test lines alike: the first sentence on its own while the rest is made (`f5_first_sentence`,
        on), a part longer than `f5_part_seconds` cut (within()), each part's statements and questions made separately
        (a question with its intonation, `shape`) with GAP between, each take checked for a cut ending (_synth). Yields
        (index, parts, WAV at full loudness - the player applies the volume -, seconds of sound); a part's tail is GAP
        when another follows. `stopped()` is asked after each piece: true, and nothing more is made or yielded."""
        import numpy as np
        if not any(ch.isalnum() for ch in text):
            return                                  # nothing to say (empty, «???», «)»): no F5 call, whatever the setting
        parts = first_and_rest(text) if self.config.get("f5_first_sentence", True) else [text]
        ref, limit = self.ref_seconds[slot.id], self.config.get("f5_part_seconds", PART_SECONDS)
        parts = [piece for part in parts
                 for piece in within(part, lambda t: self.duration(slot, t, rate, character) - ref, limit)]
        for index, part in enumerate(parts):
            pieces, sr = [], 24000
            for group in sentence_groups(part):
                piece, sr = self._synth(slot, group, rate, character)
                if pieces:
                    pieces.append(np.zeros(int(sr * GAP), dtype=piece.dtype))
                pieces.append(shape(piece, sr, group, self.config.get("question_intonation")))
                if stopped():
                    return                          # stopped meanwhile: no need to finish
            wav = np.concatenate(pieces)
            last = index == len(parts) - 1
            yield index, len(parts), wav_bytes(wav, sr, 1.0, gain_db, tail=TAIL if last else GAP), len(wav) / sr

    def _whole(self, wav, sr: int, text: str, say: bool = True) -> bool:
        """Whether Whisper hears the take's last word (no Whisper: assumed cut, made again). With `log_details` the log
        says so either way - also without Whisper, so the logs tell how often a take is made again; `say` off for the
        warm-up take, under no chat line."""
        say = say and self.config.get("log_details")
        if self.checker is None:
            if say:
                self.log("    конец впритык, ещё раз длиннее (без Whisper)")
            return False
        try:
            heard = self.checker.transcribe(wav, sr)
        except Exception as e:  # noqa: BLE001 - a judge that fails must not lose the line
            self.log(f"    Whisper: {e}")
            return False
        whole = ending_heard(text, heard)
        if say:
            self.log(f"    конец {'цел' if whole else 'обрезан, ещё раз длиннее'} (Whisper: «{heard.strip()}»)")
        return whole

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
            self.error = str(e) or type(e).__name__     # never "": that would read as success
            self.models_missing = models_missing(e)
            self.ready.set()
            return
        self.ready.set()
        while True:
            self.working = False
            line = self.lines.get()
            self.working = True
            if line is None:                 # shutdown: free the model and the GPU memory
                self.onnx = self.checker = None
                import gc
                gc.collect()
                return
            generation = self.player.generation   # a stop while this is being made drops it
            slot = self.assigner.slot_for(line.sender, line.race, line.sex)
            if slot is None:
                continue
            text = self.spoken(line.text)
            if self.config.get("log_details"):     # always: a verdict below belongs to the last «к синтезу» (f5_endings)
                groups = sentence_groups(text)
                self.log(f"    к синтезу: {text}" + (f"  ({len(groups)} части)" if len(groups) > 1 else ""))
            started = time.perf_counter()
            received = line.received if self.config.get("log_details") else None
            try:
                # in the try too: a gain typed wrong in config.json ("yell": null) costs the line, not the thread
                gain = self.config["kind_gain_db"].get(line.kind, 0)
                for index, count, data, sound in self.render(slot, text, line.rate, line.sender, gain,
                                                             lambda: generation != self.player.generation):
                    if self.config.get("debug"):
                        self.log(f"  синтез {time.perf_counter() - started:.2f} с, {sound:.1f} с звука"
                                 + (f" (часть {index + 1} из {count})" if count > 1 else ""))
                    self.player.play(data, generation, received if index == 0 else None)
            except Exception as e:  # noqa: BLE001 - one bad line must not stop the reader
                self.log(f"F5-TTS: {e}")
                continue

    # --- the reader's side ------------------------------------------------------------------

    def describe(self, line) -> str:
        if self.assigner is None:
            return "-"
        slot = self.assigner.slot_for(line.sender, line.race, line.sex)
        return slot.id if slot else "-"

    def clear(self) -> None:
        drain(self.lines)

    def shutdown(self) -> None:
        """Stop after the line being made; the model is freed on the synth thread."""
        if self.assigner is not None:
            self.assigner.flush()
        drain(self.lines)
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
    log(f"память: {c.WorkingSetSize / 2**30:.2f} ГБ (пик {c.PeakWorkingSetSize / 2**30:.2f})")
    log(f"файлы: {out}")
    return 0
