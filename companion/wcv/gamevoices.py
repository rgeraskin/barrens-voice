"""The voice bank for F5-TTS: reference clips made from the recordings in the game client itself.

The client's Russian voice-over has, per race and sex, the player character's voice (error
messages such as "Недостаточно маны", and calm emotes) and several NPC voice types (greetings,
farewells). `game_voices.json` (made by tools/game_voices.py) lists which files those are; here
they are read out of the local CASC storage (read only: `casc.py`), heard by Whisper for their
text (the client has no subtitles for them), and a few calm lines of each voice are put together
into one reference clip of 5..10 s. Each voice also gets copies shifted in pitch, so characters of
one race and sex can sound apart. Nothing of the game is shipped: the bank is made on the player's
machine, once per game build (kept in voices/ with the build key it came from).
"""
from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass
from pathlib import Path

from .dictionary import wow_roots

BANK_VERSION = 6
SAMPLE_RATE = 24000
TABLE = Path(__file__).with_name("game_voices.json")
GAP = 0.15            # seconds of silence between the lines of a reference clip
TARGET = (5.5, 9.5)   # seconds of speech wanted in a reference clip
MAX_LINES = 4
MIN_SPEECH = 3.0      # seconds: a voice with less usable speech than this gets no reference clip
GOOD = 0.8            # the joined clip heard back by Whisper must match its text at least this well
# Whisper's hallucinations on short or wordless clips
JUNK = re.compile(r"продолжение следует|субтитр|спасибо за просмотр|редактор|корректор|подпис", re.I)


@dataclass(frozen=True)
class Slot:
    """One voice a character can be given: a reference clip, its text and how long the speech in it
    is (without the pauses between its lines: the pace of the voice)."""
    id: str          # "orc-male", "orc-male/standard", "orc-male/standard^+1.5" for a pitch-shifted copy
    base: str        # the voice it is a copy of
    race: str        # "orc", "scourge", ...
    sex: str         # "male", "female"
    shift: float     # semitones
    path: str
    text: str
    speech: float = 0.0


def find_game(config: dict) -> tuple[Path, Path] | None:
    """(the WoW install with the storage, its game folder) - Forever first. The game folder must
    exist and its product be installed there (one install can hold several games, and several
    installs can sit on different drives)."""
    from .casc import build_info, product_of

    def usable(root: Path) -> bool:
        if not (root.is_dir() and (root.parent / ".build.info").exists() and (root.parent / "Data").is_dir()):
            return False
        try:
            build_info(root.parent, product_of(root))
            return True
        except (LookupError, OSError):
            return False

    roots = wow_roots(config)
    for flavor in ("_forever_", "_retail_"):
        for root in roots:
            if root.name == flavor and usable(root):
                return root.parent, root
    for root in roots:                                 # a wow_dir pointing at some other game folder
        if usable(root):
            return root.parent, root
    return None


def _stamp(config: dict, shifts) -> dict | None:
    """What the bank depends on; None when no game is found."""
    from .casc import build_info, product_of
    found = find_game(config)
    if not found:
        return None
    install, flavor = found
    product = product_of(flavor)
    try:
        build = build_info(install, product)["Build Key"]
    except (LookupError, KeyError, OSError):
        return None
    return {"version": BANK_VERSION, "install": str(install), "product": product, "build": build,
            "shifts": list(shifts), "table": TABLE.stat().st_size}


def load(out: Path, stamp: dict | None) -> list[Slot] | None:
    manifest = out / "bank.json"
    if stamp is None or not manifest.exists():
        return None
    saved = json.loads(manifest.read_text(encoding="utf-8"))
    if saved.get("stamp") != stamp:
        return None
    return [Slot(**s) for s in saved["slots"]]


def stale(config: dict, out: Path) -> bool:
    """Whether the bank has to be (re)made: no bank, another game build, other settings."""
    stamp = _stamp(config, config.get("voice_shifts", []))
    return stamp is not None and load(out, stamp) is None


# --- choosing the lines -------------------------------------------------------------------------

def plausible(text: str, seconds: float) -> bool:
    """A transcript worth trusting: Russian words at a speaking pace. Short shouts and wordless
    sounds come back from Whisper as made-up sentences ("Заг-заг" as a whole phrase)."""
    text = text.strip()
    letters = len(re.findall(r"[а-яё]", text, re.I))
    if not letters or JUNK.search(text) or re.search(r"[a-z]{3}", text, re.I):
        return False
    if re.search(r"(ха-?){2}|ля-ля|хей", text, re.I):
        return False
    return 0.9 <= seconds <= 7.5 and 5 <= letters / seconds <= 22


def choose(lines: list[dict]) -> list[dict]:
    """The lines for a reference clip from heard ones ({"text", "seconds", "priority"}), in order:
    the calmest first, up to MAX_LINES and TARGET seconds of speech; at most one question, and the
    clip ends with a statement (F5 continues the reference: its last line sets the tone)."""
    picked: list[dict] = []
    total = 0.0
    question = False
    for line in sorted(lines, key=lambda x: (x["priority"], abs(x["seconds"] - 3.0))):
        if len(picked) >= MAX_LINES or total >= TARGET[0]:
            break
        is_q = line["text"].rstrip().endswith("?")
        if (is_q and question) or total + line["seconds"] > TARGET[1]:
            continue
        picked.append(line)
        total += line["seconds"]
        question = question or is_q
    statements = [x for x in picked if not x["text"].rstrip().endswith("?")]
    if statements and picked[-1] not in statements:
        picked.remove(statements[-1])
        picked.append(statements[-1])
    return picked


def joined_text(lines: list[dict]) -> str:
    texts = []
    for line in lines:
        t = re.sub(r"[«»\"„“”]", "", line["text"]).strip()
        texts.append(t if t[-1:] in ".!?…" else t + ".")
    return " ".join(texts)


# --- audio --------------------------------------------------------------------------------------

def _decode(data: bytes):
    import numpy as np
    import soundfile as sf

    samples, rate = sf.read(io.BytesIO(data), dtype="float32", always_2d=True)
    mono = samples.mean(axis=1)
    if rate != SAMPLE_RATE:
        mono = np.interp(np.linspace(0, len(mono) - 1, int(len(mono) * SAMPLE_RATE / rate)),
                         np.arange(len(mono)), mono).astype("float32")
    return _trim(mono)


def _trim(x):
    import numpy as np

    a = np.abs(x)
    if not len(a) or a.max() == 0:
        return x
    loud = np.flatnonzero(a > a.max() * 0.03)
    pad = int(0.03 * SAMPLE_RATE)
    return x[max(0, loud[0] - pad):loud[-1] + pad]


def _join(clips):
    """The lines one after another, each at the same loudness, with short pauses."""
    import numpy as np

    gap = np.zeros(int(GAP * SAMPLE_RATE), dtype="float32")
    parts = []
    for x in clips:
        parts += [x / (np.sqrt(np.mean(x ** 2)) + 1e-9) * 0.08, gap]
    wav = np.concatenate(parts[:-1])
    peak = float(np.abs(wav).max())
    return wav / peak * 0.95 if peak > 0.95 else wav


def _shift(samples, semitones: float):
    """Pitch shift by resampling: a little higher (or lower) and a little faster (or slower) -
    for a reference clip that is only a different, still natural voice."""
    import numpy as np

    factor = 2 ** (semitones / 12)
    n = int(len(samples) / factor)
    return np.interp(np.linspace(0, len(samples) - 1, n), np.arange(len(samples)), samples).astype("float32")


# --- the bank -----------------------------------------------------------------------------------

def build(config: dict, out: Path, log, checker) -> list[Slot]:
    """The bank: kept as it is while the game build and settings are the same, else made again
    from the client with `checker` (a loaded refcheck.Checker: Whisper)."""
    shifts = config.get("voice_shifts", [])
    stamp = _stamp(config, shifts)
    if stamp is None:
        raise RuntimeError("не найдена папка игры (укажите wow_dir в config.json)")
    slots = load(out, stamp)
    if slots is not None:
        return slots
    if checker is None:
        raise RuntimeError("для голосов из клиента нужна модель Whisper (распознать текст реплик)")
    import soundfile as sf

    from .casc import Storage

    log(f"готовлю голоса рас из клиента игры ({stamp['install']}, {stamp['product']}) — один раз после "
        "каждого обновления игры, несколько минут ...")
    table = json.loads(TABLE.read_text(encoding="utf-8"))["voices"]
    storage = Storage(Path(stamp["install"]), stamp["product"])
    files = storage.read_files({f[0] for v in table.values() for f in v["files"]}, "ruRU")
    log(f"русских реплик в клиенте: {len(files)}")
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.wav"):
        old.unlink()
    slots: list[Slot] = []
    skipped = []
    for voice, entry in sorted(table.items()):
        heard: list[dict] = []
        audio: dict[int, object] = {}
        candidates = [f for f in entry["files"] if f[0] in files]
        # the calmest first, then lines of about 3 s; heard one by one only until there are enough
        candidates.sort(key=lambda f: f[2])
        for fdid, _tag, priority in candidates:
            try:
                x = _decode(files[fdid])
            except Exception:  # noqa: BLE001 - one unreadable file does not matter
                continue
            seconds = len(x) / SAMPLE_RATE
            if not 0.9 <= seconds <= 7.5:
                continue
            text = checker.transcribe(x, SAMPLE_RATE).strip()
            if plausible(text, seconds):
                heard.append({"fdid": fdid, "text": text, "seconds": seconds, "priority": priority})
                audio[fdid] = x
            if sum(h["seconds"] for h in heard if h["priority"] == heard[0]["priority"]) >= TARGET[1] * 1.5:
                break
        made = None
        pool = list(heard)
        for _ in range(3):
            lines = choose(pool)
            if sum(x["seconds"] for x in lines) < MIN_SPEECH:
                break
            wav, text = _join([audio[x["fdid"]] for x in lines]), joined_text(lines)
            score, _ = checker.score(wav, SAMPLE_RATE, text)
            if score >= GOOD:
                made = (wav, text, sum(x["seconds"] for x in lines))
                break
            pool.remove(min(lines, key=lambda x: x["seconds"]))   # the shortest line is the likeliest wrong
        if made is None:
            skipped.append(voice)
            continue
        wav, text, speech = made
        safe = voice.replace("/", "_")
        for shift in [0.0] + list(shifts):
            slot_id = voice if shift == 0 else f"{voice}^{shift:+g}"
            path = out / (f"{safe}.wav" if shift == 0 else f"{safe}_{shift:+g}.wav")
            sf.write(str(path), wav if shift == 0 else _shift(wav, shift), SAMPLE_RATE)
            # a shifted copy is played faster or slower by the same factor
            slots.append(Slot(slot_id, voice, entry["race"], entry["sex"], shift, str(path), text,
                              round(speech / 2 ** (shift / 12), 3)))
    (out / "bank.json").write_text(json.dumps({"stamp": stamp, "slots": [s.__dict__ for s in slots]},
                                              ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"голосов рас: {len({s.base for s in slots})}, вариантов с тембром: {len(slots)}"
        + (f"; без голоса (мало реплик): {', '.join(skipped)}" if skipped else ""))
    return slots
