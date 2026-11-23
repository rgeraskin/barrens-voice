"""The voice lab: what each race voice's reference clip is made of, to hear and choose by ear.

`python -m bv --voicelab <folder> [--only <voice>] [--no-f5] [--steps 6[,8]]` (with the game and the voice-over closed: Whisper
and F5 take the video card). For every voice of the chosen game, a folder (`troll-female/old`):
- `all/`: every line of the voice in the client, "<file id> <kind> <text>.wav" (a line the bank would never take -
  too short or long, or a transcript not worth trusting - with «(не годится)»);
- `used/`: the lines its reference clip is made of, in order;
- `sample.wav`: the clip itself (`sample.txt` its text) - what F5 imitates;
- `test.wav`: `test_text` spoken by F5 with that clip; with `--steps 6`, `test-6.wav` too: the same line in 6 steps
  instead of 10 (f5_schedule), to hear whether the faster F5 is as good.
And `voices.yaml` beside them: every voice with all its lines, the used ones as list items, the rest commented out.
Edit it (comment a line out, take one in, reorder) and run again: the clips and test lines are made from it,
the transcripts are not heard again (`transcripts.json`). Copied to companion/bv/voice_picks.yaml, it is what
the players' banks are made of (gamevoices.PICKS).
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from . import gamevoices

LAB_FILE = "voices.yaml"
TRANSCRIPTS = "transcripts.json"
AUTO = "auto.json"        # each voice's automatic choice (as the bank makes it): --pick carries only what differs
PACES = "paces.json"      # the bank's target pace of the last full run: --only's test lines in the game's tempo
# no chat abbreviations: the lab's F5 gets the text without the addon's dictionary
TEST_TEXT = "Нужен танк в Мёртвые копи, продам сумки за 5000. Кто со мной?"
KINDS = {"error": "ошибка", "greeting": "приветствие", "farewell": "прощание", "vendor": "торговля",
         "pissed": "раздражение", "line": "реплика"}


def parse_args(args: list[str]):
    """`--voicelab`'s switches after it: (the folder, --only's voice or "", whether F5 speaks, --steps' numbers of
    steps), or the usage line."""
    from .f5_schedule import STEPS
    if not args or args[0].startswith("--"):
        return "--voicelab <папка> [--only <голос>] [--no-f5] [--steps 6[,8]]"
    only = ""
    if "--only" in args:
        at = args.index("--only") + 1
        if at >= len(args) or args[at].startswith("--"):
            return "--only <голос>: например --only troll-female/old"
        only = args[at]
    steps: tuple[int, ...] = ()
    if "--steps" in args:
        at = args.index("--steps") + 1
        given = args[at].split(",") if at < len(args) else []
        if not given or not all(n.strip().isdigit() and int(n) in STEPS for n in given):
            return f"--steps <шаги>: {', '.join(map(str, STEPS))} или несколько через запятую — например --steps 6,8"
        steps = tuple(sorted({int(n) for n in given}))
    return Path(args[0]), only, "--no-f5" not in args, steps


def kind_of(tag: str) -> str:
    """The line's kind as the lab file says it: «прощание», an emote's own tag («hello») as it is."""
    return KINDS.get(tag, tag)


def file_name(*parts) -> str:
    """A file name of `parts` that Windows takes: no reserved marks, not too long."""
    name = " ".join(str(p) for p in parts if p != "")
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name).strip(" .")
    return name[:90].rstrip(" .")


def quoted(text: str) -> str:
    """`text` in double quotes as YAML reads it back: JSON's quoting, and \\u escapes for what YAML takes otherwise
    (U+0085 is a line break to it, U+007F-U+009F and a lone surrogate are not allowed in its files)."""
    return re.sub(r"[\x7f-\x9f\ud800-\udfff]", lambda m: f"\\u{ord(m.group()):04x}",
                  json.dumps(text, ensure_ascii=False))


class LabStop(RuntimeError):
    """The run stops with a message for the one at the keyboard (a file open in another program)."""


def read_lab(path: Path) -> tuple[dict[str, list[tuple[int, str | None]]], str]:
    """(the picks with their texts, the test text) of a lab file; ({}, TEST_TEXT) without one."""
    if not path.exists():
        return {}, TEST_TEXT
    import yaml
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return gamevoices.load_lines(path), str(data.get("test_text") or TEST_TEXT)


def lab_text(voices: list[tuple[str, list[dict], list[int]]], test_text: str) -> str:
    """The lab file: for each voice (id, its heard lines, the used files in order) every line, the used ones as
    list items in their order first, the others commented out after them."""
    out = [
        "# Голоса рас: из каких фраз игры собран образец каждого голоса (python -m bv --voicelab).",
        "# Строка без «#» — фраза в образце, по порядку; закомментируй фразу, чтобы убрать её, раскомментируй, чтобы",
        "# добавить, переставь строки, чтобы сменить порядок. Голос, у которого все фразы закомментированы, не",
        "# используется. Последней лучше ставить спокойное утверждение: F5 продолжает тон конца образца.",
        "# Образец — 5–10 секунд речи. «(не годится)»: сборка сама такую фразу не взяла бы (длина или текст).",
        "# Текст в кавычках — текст фразы в образце: Whisper ослышался — поправь его здесь (F5 читает образец с ним).",
        "# Голос, которого здесь нет, берёт выбор из companion/bv/voice_picks.yaml, а без него — как сборка банка.",
        "# Чтобы так собирались образцы у игроков: mise run voicelab -- --pick (голоса этого файла — в voice_picks.yaml).",
        "",
        f"test_text: {quoted(test_text)}",
        "",
        "voices:",
    ]
    for voice, heard, used in voices:
        out.append(f"  {voice}:")
        by_id = {h["fdid"]: h for h in heard}
        rest = sorted((h for h in heard if h["fdid"] not in used), key=lambda h: (h["priority"], h["fdid"]))
        for fdid in used:
            if fdid not in by_id:                               # kept as chosen: the log says why it is not heard
                out.append(f"    - {fdid}  # нет среди реплик этого голоса на диске")
                continue
            out.append(line_text("", by_id[fdid]))
        out += [line_text("# ", h) for h in rest]
    return "\n".join(out) + "\n"


def line_text(prefix: str, line: dict) -> str:
    """A line as the lab file writes it: its id and its text (the clip's own: the bank takes it as written), then
    its kind and length in a comment; a line with no words heard - its id alone."""
    note = "" if line["usable"] else " (не годится)"
    about = f"{kind_of(line['tag'])}, {line['seconds']:.1f} с{note}"
    if not line["text"]:
        return f"    {prefix}- {line['fdid']}  # {about}: …"
    return f"    {prefix}- {line['fdid']}: {quoted(line['text'])}  # {about}"


def written(heard: list[dict], used: list[int]) -> list[tuple[int, str | None]]:
    """A voice's used lines as `lab_text` writes them: (id, its text, or None when it has none or is not heard)."""
    by_id = {h["fdid"]: h for h in heard}
    return [(fdid, (by_id[fdid]["text"] or None) if fdid in by_id else None) for fdid in used]


def blocks(text: str) -> dict[str, str]:
    """A lab or picks file's voices, each its block of lines as written ("  orc-male:\\n    - 1  # ...\\n")."""
    if "\nvoices:" not in "\n" + text:
        return {}
    body = ("\n" + text).split("\nvoices:", 1)[1].split("\n", 1)
    parts = re.split(r"(?m)^(?=  \S[^\n]*:\s*$)", body[1] if len(body) > 1 else "")   # «  # голос:» too
    return {b.split(":", 1)[0].strip(): b if b.endswith("\n") else b + "\n" for b in parts if b.strip()}


def with_blocks(head: str, kept: dict[str, str]) -> str:
    """`head` (comments, test_text) and the voices' blocks, sorted; «voices: {}» when there are none."""
    if not kept:
        return head + "voices: {}\n"
    return head + "voices:\n" + "".join(kept[v] for v in sorted(kept))


def corrected(lines: list[tuple[int, str | None]], heard: dict[int, str]) -> bool:
    """Whether a text of `lines` was changed by hand: other than Whisper heard it (`heard`, transcripts.json)."""
    return any(said is not None and fdid in heard and said != (heard[fdid] or "").strip() for fdid, said in lines)


def lines_or_stop(text: str, what: str) -> dict:
    """`text`'s voices (gamevoices.lines_of), or ValueError with a message instead of YAML's traceback."""
    import yaml
    try:
        return gamevoices.lines_of(text) if text.strip() else {}
    except yaml.YAMLError as e:
        raise ValueError(f"{what} не читается как YAML: {e} — текст с двоеточием пиши в кавычках") from e
    except (ValueError, TypeError, AttributeError) as e:   # YAML, but not voices with their lines
        raise ValueError(f"{what}: {e} — запиши голоса так, как пишет лаборатория") from e


def check_shape(text: str, what: str) -> None:
    """ValueError when a block of `text` (as `blocks` finds them) is not exactly its own voice, or the blocks do not
    add up to the file: a hand-written voice glued to another's block would be lost when that block is rewritten."""
    whole = lines_or_stop(text, what)
    found: dict = {}
    for voice, block in blocks(text).items():
        alone = lines_or_stop("voices:\n" + block, what)
        if voice.startswith("#") and not alone:
            continue                                       # a voice commented out whole: kept as it is, no lines
        if list(alone) != [voice]:
            wrong = sorted(set(alone) | {voice})
            raise ValueError(f"{what}: не получится переписать голоса {', '.join(wrong)} — запиши их так, как пишет "
                             "лаборатория («  голос:», под ним «    - номер» или «    - номер: \"текст\"» по строке)")
        found.update(alone)
    if found != whole:
        wrong = sorted(v for v in set(found) | set(whole) if found.get(v) != whole.get(v))
        raise ValueError(f"{what}: не получится переписать голоса {', '.join(wrong)} — запиши их так, как пишет "
                         "лаборатория")


def checked(text: str, expected: dict[str, list[tuple[int, str | None]]], what: str) -> str:
    """`text` if it reads (as YAML) as `expected`, else ValueError: the blocks are found by the lines' shape, and a
    hand-written voice of another shape (``orc-male: [1, 2]``, a comment after the name) is not one of them."""
    try:
        got = gamevoices.lines_of(text)
    except Exception as e:  # noqa: BLE001 - any YAML error: the same message
        got = {"<не YAML>": [(0, str(e))]}
    if got != expected:
        wrong = sorted(v for v in set(got) | set(expected) if got.get(v) != expected.get(v))
        raise ValueError(f"{what}: не получилось переписать голоса {', '.join(wrong)} — запиши их так, как пишет "
                         "лаборатория («  голос:», под ним «    - номер» или «    - номер: \"текст\"» по строке)")
    return text


def write_voice(folder: Path, heard: list[dict], audio: dict, made) -> None:
    """A voice's folder: all/, used/, sample.wav and sample.txt (none when the voice has no clip)."""
    import soundfile as sf
    try:
        _write_voice(folder, heard, audio, made)
    except LabStop:
        raise
    except (OSError, sf.SoundFileError) as e:   # on Windows: a file open in a player; the lab's own bugs as they are
        raise LabStop(f"не записать {folder}: {e} — закрой его файлы в других программах и запусти снова") from e


def _write_voice(folder: Path, heard: list[dict], audio: dict, made) -> None:
    import soundfile as sf
    for old in ("all", "used"):
        shutil.rmtree(folder / old, ignore_errors=True)
    for old in ("sample.wav", "sample.txt", "test.wav", *(f.name for f in folder.glob("test-*.wav"))):
        try:
            (folder / old).unlink(missing_ok=True)
        except PermissionError as e:                         # Windows: open in a player
            raise LabStop(f"{folder / old} открыт в другой программе — закрой его и запусти снова") from e
    (folder / "all").mkdir(parents=True, exist_ok=True)       # a file open in a player keeps the folder (Windows)
    for h in heard:
        note = "" if h["usable"] else "(не годится)"           # before the text: a long one is cut, the note stays
        sf.write(str(folder / "all" / (file_name(h["fdid"], kind_of(h["tag"]), note, h["text"]) + ".wav")),
                 audio[h["fdid"]], gamevoices.SAMPLE_RATE)
    if made is None:
        return
    wav, text, _speech, used = made
    (folder / "used").mkdir(exist_ok=True)
    by_id = {h["fdid"]: h for h in heard}
    for n, fdid in enumerate(used, 1):
        sf.write(str(folder / "used" / (file_name(n, fdid, by_id[fdid]["text"]) + ".wav")), audio[fdid],
                 gamevoices.SAMPLE_RATE)
    sf.write(str(folder / "sample.wav"), wav, gamevoices.SAMPLE_RATE)
    (folder / "sample.txt").write_text(text + "\n", encoding="utf-8")


def run(config: dict, home: Path, out: Path, log, only: str = "", f5: bool = True, steps: tuple[int, ...] = ()) -> int:
    """The lab in `out` for the chosen game's voices (`only`: those whose id has it; `steps`: the test line also in
    these numbers of steps)."""
    from .casc import Storage
    from .f5engine import preload, provider
    from .whisper_onnx import OnnxChecker

    stamp = gamevoices._stamp(config, [])
    if stamp is None:
        log("не найдена папка игры (wow_dir в config.json)")
        return 1
    out.mkdir(parents=True, exist_ok=True)
    old = (out / LAB_FILE).read_text(encoding="utf-8") if (out / LAB_FILE).exists() else ""
    try:
        check_shape(old, LAB_FILE)                          # a file the lab could not write back: stop before the work
        picks, test_text = read_lab(out / LAB_FILE)
    except ValueError as e:
        log(str(e))
        return 1
    shipped = gamevoices.load_lines()                       # for a voice the lab file does not have yet
    auto_path, paces_path = out / AUTO, out / PACES
    auto = json.loads(auto_path.read_text(encoding="utf-8")) if auto_path.exists() else {}
    table = {v: e for v, e in gamevoices.voices_for(config).items() if only in v}
    storage = Storage(Path(stamp["install"]), stamp["product"])
    files = storage.read_files({f[0] for e in table.values() for f in e["files"]}, "ruRU",
                               gamevoices.other_storages(config, log))
    log(f"голосов: {len(table)}, русских реплик: {len(files)}")
    known_path = out / TRANSCRIPTS
    known = {int(k): v for k, v in json.loads(known_path.read_text(encoding="utf-8")).items()} \
        if known_path.exists() else {}
    engine = provider(config)
    preload(engine)
    checker = OnnxChecker(log, engine)
    if not checker.load():
        log("Whisper не загрузился")
        return 1
    lab, clips = [], {}
    try:
        for n, (voice, entry) in enumerate(sorted(table.items()), 1):
            heard, audio = gamevoices.listen(entry["files"], files, checker, enough=False, known=known)
            chosen_lines = picks[voice] if voice in picks else shipped.get(voice)
            for fdid, said in picks.get(voice, []):
                if said is not None and fdid in known and said != (known[fdid] or "").strip():
                    log(f"{voice}: текст фразы {fdid} не как у Whisper — оставлен как выбор на слух")
            if voice in picks and [f for f, _ in picks[voice]] == auto.get(voice) and not corrected(picks[voice], known):
                # the lab file has the automatic choice of its last run, untouched: it follows the automatic choice
                # (a game update, another transcript) instead of keeping the old one as a choice by ear
                chosen_lines = None
            picked = [fdid for fdid, _ in chosen_lines] if chosen_lines is not None else None
            # the automatic choice, as the bank makes it (among what it would hear): kept for --pick, and the clip
            # when nothing is chosen by ear
            calmest = min((f[2] for f in entry["files"] if f[0] in files), default=1)
            chosen = gamevoices.reference(gamevoices.bank_pool(heard, calmest), audio, checker)
            auto[voice] = chosen[3] if chosen else []
            if picked is None:
                made = chosen
            else:
                # a text the file gives is the line's (corrected by hand, or as the players' file has it)
                given: dict[int, str] = {}
                for fdid, said in chosen_lines:                 # a line listed twice: the copy corrected by hand
                    if said and (fdid not in given or said != (known.get(fdid) or "").strip()):
                        given[fdid] = said
                heard = [dict(h, text=given[h["fdid"]], usable=0.9 <= h["seconds"] <= 7.5 and
                              gamevoices.plausible(given[h["fdid"]], h["seconds"])) if h["fdid"] in given else h
                         for h in heard]
                made = gamevoices.reference(heard, audio, checker, picked) if picked else None
                tell_picked(voice, picked, heard, made, log)
            write_voice(out / voice, heard, audio, made)
            # a choice by ear stays in the file as it is, clip or not: it is the player's to change
            lab.append((voice, heard, picked if picked is not None else (made[3] if made else [])))
            if made:
                clips[voice] = made
            log(f"{n}/{len(table)} {voice}: фраз {len(heard)}, в образце {len(made[3]) if made else 0}"
                + (" (выбрано вручную)" if picked is not None and picked != auto[voice] else ""))
    except LabStop as e:                                    # a file open in another program: said, not a traceback
        log(str(e))
        return 1
    finally:                                                # only a cache: what was heard is kept whatever comes
        known_path.write_text(json.dumps({str(k): v for k, v in sorted(known.items())}, ensure_ascii=False, indent=1),
                              encoding="utf-8")
    # the voices heard now written anew, the others (--only, the other game's) kept as they were
    try:
        (out / LAB_FILE).write_text(merge_lab(old, lab, test_text), encoding="utf-8")
    except ValueError as e:
        log(str(e))
        return 1
    # with the lab file it goes with, not before: a run stopped midway (a file open in a player, Ctrl+C) would leave
    # the old lab file's lists beside new automatic choices - and those lists taken for choices by ear
    auto_path.write_text(json.dumps(dict(sorted(auto.items())), indent=1), encoding="utf-8")
    checker.encoder = checker.decoder = None
    if f5 and clips:
        saved = json.loads(paces_path.read_text(encoding="utf-8")).get("target") if paces_path.exists() else None
        try:
            target = speak(config, home, out, clips, test_text, log, saved if only else None, steps)
        except ValueError as e:                             # --steps: a model it does not know, no onnx package
            log(f"сокращённое расписание F5: {e}")
            return 1
        if not only:
            paces_path.write_text(json.dumps({"target": target}), encoding="utf-8")
    log(f"готово: {out}")
    return 0


def merge_lab(old: str, lab: list, test_text: str) -> str:
    """The lab file with the voices of `lab` written anew, the other voices' blocks of `old` kept as they are."""
    kept = blocks(old)
    for voice, heard, used in lab:
        kept.update(blocks(lab_text([(voice, heard, used)], test_text)))
    expected = {**lines_or_stop(old, LAB_FILE), **{voice: written(heard, used) for voice, heard, used in lab}}
    return checked(with_blocks(lab_text([], test_text).rsplit("voices:", 1)[0], kept), expected, LAB_FILE)


def to_picks(lab: str, picks: str, auto: dict, head: str, heard: dict | None = None) -> str:
    """voice_picks.yaml (`picks`) with the lab's choices by ear: a lab voice whose list differs from its automatic
    choice (`auto`, the lab's auto.json), or with a text corrected by hand (other than Whisper heard it: `heard`, the
    lab's transcripts.json), is written in as the lab has it, texts and all; one that is the automatic choice again
    goes from the file (the bank chooses it itself); the voices the lab has not heard stay as they were."""
    heard = {int(k): v for k, v in (heard or {}).items()}
    lab_lines, expected = lines_or_stop(lab, LAB_FILE), lines_or_stop(picks, "voice_picks.yaml")
    unknown = sorted(voice for voice in lab_lines if voice not in auto)
    if unknown:
        # a lab made before auto.json, continued with --only: these voices' automatic choice is not known
        raise ValueError(f"в auto.json нет голосов {', '.join(unknown)} — запусти лабораторию раз без --only")
    kept, lab_blocks = blocks(picks), blocks(lab)
    for voice, lines in lab_lines.items():
        used = [fdid for fdid, _ in lines]
        if used == auto[voice] and not corrected(lines, heard):
            kept.pop(voice, None)
            expected.pop(voice, None)
        else:
            kept[voice] = lab_blocks.get(voice, "")          # a voice of another shape: `checked` says so
            expected[voice] = lines
    return checked(with_blocks(head, kept), expected, "voice_picks.yaml")


def tell_picked(voice: str, picked: list[int], heard: list[dict], made, log) -> None:
    """What of a choice by ear did not go into the clip, and a clip too short or too long, in the log."""
    by_id = {h["fdid"]: h for h in heard}
    for fdid in picked:
        if fdid not in by_id:
            log(f"{voice}: {fdid} не взят — не реплика этого голоса или её нет на диске")
        elif not by_id[fdid]["text"]:
            log(f"{voice}: {fdid} не взят — Whisper не расслышал в ней слов")
    speech = sum(by_id[f]["seconds"] for f in picked if f in by_id and by_id[f]["text"])
    if picked and made is None:
        log(f"{voice}: образец не собран — речи {speech:.1f} с, нужно от {gamevoices.MIN_SPEECH:g} с")
    elif made and not gamevoices.TARGET[0] <= speech <= gamevoices.TARGET[1]:
        log(f"{voice}: речи в образце {speech:.1f} с — F5 лучше {gamevoices.TARGET[0]:g}–{gamevoices.TARGET[1]:g} с")


def speak(config: dict, home: Path, out: Path, clips: dict, test_text: str, log, target: float | None = None,
          steps: tuple[int, ...] = ()) -> float:
    """`test_text` spoken by F5 with each voice's clip: test.wav in its folder, and test-<n>.wav in each of `steps`
    numbers of steps (f5_schedule: the Transformer rewritten once into the lab's f5-steps folder). `target`: the
    bank's target pace (a full run's, for --only), else of these clips; the one used is returned."""
    import soundfile as sf
    from huggingface_hub import hf_hub_download

    from .f5engine import MODEL_REPO, VOCAB_FILE, fetch_models, line_seconds, model_dir, provider
    from .f5_schedule import transformer
    from .f5onnx import F5Onnx
    from .text import Accentor, numbers_to_words
    from .whisper_onnx import resample

    models = model_dir(config, home) or fetch_models(config, log)
    vocab = Path(hf_hub_download(MODEL_REPO, VOCAB_FILE))
    onnx = F5Onnx(models, vocab, provider(config), log)
    onnx.load()
    accentor = Accentor(log, config.get("ruaccent", True))
    accentor.load()
    text = accentor.accent(numbers_to_words(test_text))
    refs = {voice: accentor.accent(clip[1]) for voice, clip in clips.items()}
    paces = {voice: clips[voice][2] / max(1, len(refs[voice].encode("utf-8"))) for voice in clips}
    # the bank's target pace, as F5Speaker._load takes it: of the clips of a full run
    if target is None:
        ordered = sorted(paces.values())
        target = ordered[min(len(ordered) - 1, int(len(ordered) * config.get("voice_pace_quantile", 0.25)))]
    try:                                                    # before any test line: a refusal writes none
        fewer = {n: transformer(onnx.net_file, out / "f5-steps", n) for n in steps}
    except ImportError as e:
        raise ValueError("нет пакета onnx: его ставит в папку лаборатории mise run voicelab -- --steps …") from e
    for n in (None, *steps):
        if n:
            onnx = None                                     # one model on the card at a time
            onnx = F5Onnx(models, vocab, provider(config), log, (fewer[n], n))
            onnx.load()
        for voice, (wav, _text, _speech, _used) in sorted(clips.items()):
            ref_text = refs[voice]
            ref_seconds = len(wav) / gamevoices.SAMPLE_RATE
            total = ref_seconds + line_seconds(paces[voice], target, len(text.encode("utf-8")), 100, "", config)
            spoken, rate = onnx.synth(resample(wav, gamevoices.SAMPLE_RATE, onnx.in_rate), ref_text, text, total)
            sf.write(str(out / voice / (f"test-{n}.wav" if n else "test.wav")), spoken, rate)
            log(f"F5{f' ({n} из 10 шагов)' if n else ''}: {voice}")
    return target
