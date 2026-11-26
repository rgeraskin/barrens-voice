"""Why race voices cut their endings (docs/bugs.md): chat lines from a companion log, made again with F5 at the length
the program gives them and longer, and per take the quiet after the speech and what Whisper hears.

  cases <bv-YYYY-MM-DD.log> <cases.json> [cut] [whole] [--exact]   the lines Whisper judged in the log (log_details, f5_end_check
                                    "whisper"): their text as F5 got it («к синтезу»), their voice and the verdict -
                                    the last `cut` (10) judged cut and `whole` (6) judged whole. The players' lines stay
                                    in that file: keep it out of the repository. --exact: a log from 0.6.0b3 on
                                    (every line has its «к синтезу»).
  lab <cases.json> <out folder> [factors] [rate]   on the Windows machine, game and companion closed or with the player's OK:
                                    each line at the program's length times each factor (1,1.25,1.5) of its speech;
                                    NN-xF.wav for the ear and results.json. One take each: why verdicts come, not rates.
                                    `rate`: the addon's speed the player had (100; SavedVariables ["rate"]).

lab reads bv from BV_CODE (an install's companion folder, only read), data from BV_DATA and its cache from BV_CACHE
(copies: the speaker writes assignments.json and cache\\f5-steps), HF_HOME/HF_HUB_OFFLINE for the models. Over SSH an
install's .venv\\Scripts\\python.exe (uv's launcher) does not reach the base Python through the install's links: run the
base Python and give the install's site-packages as BV_SITE.
"""
from __future__ import annotations

import json
import os
import re
import site
import sys
from pathlib import Path

CHAT = re.compile(r"\d\d:\d\d:\d\d CHAT  \[[^\]]*\] (.+?) \((?:\w+|\?)(?:, [мж])?\) → ([\w/^+.-]+): (.*)$")
FLOOR = 0.6       # a match under it is no match: a Latin line Whisper heard in Cyrillic scores ~0.1 against its own text
SYNTH = re.compile(r"к синтезу: (.*?)(?:  \(\d+ части\))?$")
VERDICT = re.compile(r"конец (цел|обрезан, ещё раз длиннее) \(Whisper: «(.*)»\)$")


def plain(text: str) -> str:
    """Letters and digits only, lower case, «ё» as «е», no stress marks: for matching a log's texts."""
    return " ".join(re.findall(r"[а-яa-z0-9]+", text.lower().replace("ё", "е").replace("+", "")))


def covered(part: str, whole: str) -> float:
    """How much of `part` is found in `whole`, in order (0..1)."""
    import difflib
    part, whole = plain(part), plain(whole)
    if not part:
        return 0.0
    blocks = difflib.SequenceMatcher(None, part, whole, autojunk=False).get_matching_blocks()
    return sum(b.size for b in blocks) / len(part)


def calls(text: str) -> int:
    """About how many F5 calls a line's text makes (render(): first sentence, sentence groups; a long part is cut
    further, by its seconds - a call more for each 250 letters): the most verdicts it can have."""
    from bv import f5engine
    groups = [g for part in f5engine.first_and_rest(text) for g in f5engine.sentence_groups(part)]
    return len(groups) + len(plain(text)) // 250


def as_said(text: str) -> str:
    """A chat line's text with its numbers in words, as the program makes «к синтезу» of it (spoken(): numbers_to_words,
    then the stresses): «го 5» matches «го пять.», which a short line with a number did not."""
    from bv.text import numbers_to_words
    return numbers_to_words(text)


def digits(text: str) -> bool:
    """Whisper wrote numbers: a third of the letters and digits heard are digits."""
    signs = re.findall(r"[a-zа-яё0-9]", text.lower())
    return sum(c.isdigit() for c in signs) * 3 > len(signs)


def foreign(text: str) -> bool:
    """Mostly Latin letters or digits: a text Whisper writes otherwise (Cyrillic, digits for number words), so a weak
    match to it is to be expected."""
    signs = re.findall(r"[a-zа-я0-9]", text.lower().replace("ё", "е"))
    return sum(not ("а" <= c <= "я") for c in signs) > len(signs) / 2


def cases(lines: list[str], cut: int = 10, whole: int = 6, exact: bool = False) -> list[dict]:
    """The log's Whisper verdicts, each with the chat line it was for (the last `cut` cut ones, the last `whole` whole).
    A chat line is logged when it comes, its «к синтезу» and verdicts when the synthesis thread gets to it, in turn.
    Since 0.6.0b3 every line has its «к синтезу» (log_details): a verdict is the last one's. Older logs wrote it only for
    a changed text, so a verdict is matched by what Whisper heard (`covered`, FLOOR):
    - «к синтезу» goes to the waiting line whose text, numbers in words (`as_said`), it matches - or to the line being
      made, taken before by its verdict; under FLOOR its chat line is not in the log (the log began after it): its
      verdicts are dropped;
    - a verdict that matches the line being made, or a waiting one, goes there; a weak one stays with the line being
      made only where a weak match is to be expected for it (`foreign`: a mostly Latin text; or `digits` heard) and it
      may have more calls (`calls`) - a Cyrillic line's own verdicts match - else it goes to the oldest waiting line,
      and with none waiting it is the line being made's after all;
    - a line taken drops the waiting lines older than it (the queue dropped them, or they were made with no word in the
      log); a line with nothing to say («?») never waits. The score goes with the case («match»).
    `exact`: a log from 0.6.0b3 on, where every line made has its «к синтезу»: a verdict is the last one's. Not for an
    older log (nor the day of the update, both kinds in one file): there a line F5 got as typed has no «к синтезу», and
    its verdicts would go to the line before."""
    found, waiting, current = [], [], None
    for line in lines:
        if m := CHAT.match(line):
            if any(ch.isalnum() for ch in m[3]):                 # «?», «)»: render() makes nothing of them
                waiting = (waiting + [{"name": m[1], "voice": m[2], "text": m[3]}])[-20:]
        elif m := SYNTH.search(line):
            pool = waiting + ([current] if current and "text" in current and not current.get("made") else [])
            best = max(pool, key=lambda c: covered(m[1], as_said(c["text"])), default=None)
            if best is None or covered(m[1], as_said(best["text"])) < FLOOR:
                current = {"orphan": True}                       # its chat line is not in the log
                continue
            if best is not current:
                waiting = waiting[waiting.index(best) + 1:]
                current = {**best, "verdicts": 0}
            current.update(text=m[1], made=True, calls=calls(m[1]))
        elif m := VERDICT.search(line):
            heard = m[2]
            strong = max(waiting, key=lambda c: covered(heard, c["text"]), default=None)
            if exact:
                if not current or current.get("orphan"):
                    continue
            elif current and not current.get("orphan") and covered(heard, current["text"]) >= FLOOR:
                pass
            elif strong is not None and covered(heard, strong["text"]) >= FLOOR:
                waiting = waiting[waiting.index(strong) + 1:]
                current = {**strong, "verdicts": 0, "calls": calls(strong["text"])}
            elif (current and not current.get("orphan") and current["verdicts"] < current["calls"]
                  and (foreign(current["text"]) or digits(heard))):
                pass                                             # weak as expected, and the line may have this call
            elif current and current.get("orphan"):
                continue                                         # the verdict of a line not in the log
            elif waiting:
                current = {**waiting.pop(0), "verdicts": 0}
                current["calls"] = calls(current["text"])
            elif not current:
                continue                                         # a verdict of a line not in the log
            # else: nothing waits - the line being made is the only one it can be
            current["verdicts"] += 1
            found.append({"name": current["name"], "voice": current["voice"], "text": current["text"],
                          "verdict": "whole" if m[1] == "цел" else "cut", "heard": heard,
                          "match": round(covered(heard, current["text"]), 2)})
    picked = [c for c in found if c["verdict"] == "cut"][-cut:] if cut else []
    return picked + ([c for c in found if c["verdict"] == "whole"][-whole:] if whole else [])


def pieces(speaker, slot, text: str, character: str, rate: int = 100) -> list[str]:
    """The F5 calls render() makes of `text` at the addon's speed `rate`: the first sentence, parts within
    f5_part_seconds, sentence groups."""
    from bv import f5engine
    config = speaker.config
    parts = f5engine.first_and_rest(text) if config.get("f5_first_sentence", True) else [text]
    ref, limit = speaker.ref_seconds[slot.id], config.get("f5_part_seconds", f5engine.PART_SECONDS)
    parts = [p for part in parts
             for p in f5engine.within(part, lambda t: speaker.duration(slot, t, rate, character) - ref, limit)]
    return [group for part in parts for group in f5engine.sentence_groups(part)]


def piece_heard(speaker, slot, case: dict, rate: int = 100) -> str:
    """The piece of the case's line its verdict was for: the one whose text holds what Whisper heard best."""
    return max(pieces(speaker, slot, case["text"], case["name"], rate), key=lambda p: covered(case["heard"], p))


def lab(cases_file: str, out: str, factors: tuple[float, ...] = (1.0, 1.25, 1.5), rate: int = 100) -> None:
    """`rate`: the addon's speed («Скорость», 50..200) the player had - it is in no log line, so it is given here
    (SavedVariables BarrensVoice.lua, ["rate"]); every take's length is divided by it."""
    if os.environ.get("BV_SITE"):
        site.addsitedir(os.environ["BV_SITE"])          # the install's packages, its .pth files too (CUDA's DLLs)
    sys.path.insert(0, os.environ["BV_CODE"])
    import soundfile as sf
    from bv import f5engine
    from bv.whisper_onnx import OnnxChecker, resample
    folder = Path(out)
    folder.mkdir(exist_ok=True)
    data = Path(os.environ["BV_DATA"])
    config = json.loads((data / "config.json").read_text(encoding="utf-8"))
    config.update(f5_end_check="silence", log_details=False)
    speaker = f5engine.F5Speaker(config, lambda m: print(m, flush=True), data)
    speaker._load()
    checker = OnnxChecker(print, f5engine.provider(config))
    if not checker.load():
        raise SystemExit("Whisper did not load")
    slots = {s.id: s for s in speaker.assigner.slots}
    rows = []
    for i, case in enumerate(json.loads(Path(cases_file).read_text(encoding="utf-8"))):
        slot = slots.get(case["voice"])
        if slot is None:
            print(f"{i}: no voice {case['voice']}")
            continue
        ref = speaker.ref_seconds[slot.id]
        text = piece_heard(speaker, slot, case, rate)
        total = speaker.duration(slot, text, rate, case["name"])
        voice = resample(sf.read(slot.path, dtype="float32", always_2d=True)[0].mean(axis=1),
                         sf.info(slot.path).samplerate, speaker.onnx.in_rate)
        letters = re.findall(r"[A-Za-zА-Яа-яЁё]", text)
        row = {"i": i, "voice": case["voice"], "verdict": case["verdict"], "piece": text, "speech": round(total - ref, 2),
               "latin": round(sum(c.isascii() for c in letters) / max(1, len(letters)), 2), "takes": {}}
        for factor in factors:
            wav, rate = speaker.onnx.synth(voice, speaker.ref_text[slot.id], text, ref + (total - ref) * factor)
            quiet = float(f5engine.silence_after(wav, rate))
            heard = checker.transcribe(wav, rate).strip()
            row["takes"][str(factor)] = {"quiet": round(quiet, 3), "near_end": bool(quiet < f5engine.CUT_TAIL),
                                         "whole": bool(f5engine.ending_heard(text, heard)), "heard": heard}
            sf.write(str(folder / f"{i:02d}-x{factor:g}.wav"), wav, rate)
        rows.append(row)
        print(f"{i:2d} {case['verdict']:5s} latin {row['latin']:.2f} speech {row['speech']:4.1f} s | " + " | ".join(
            f"x{f}: quiet {t['quiet']:.3f} {'NEAR' if t['near_end'] else 'ok  '} {'whole' if t['whole'] else 'CUT  '}"
            for f, t in row["takes"].items()), flush=True)
    (folder / "results.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    command, args = sys.argv[1], sys.argv[2:]
    if command == "cases":
        log = Path(args[0]).read_text(encoding="utf-8", errors="replace").splitlines()
        exact = "--exact" in args
        args = [a for a in args if a != "--exact"]
        picked = cases(log, *(int(a) for a in args[2:4]), exact=exact)
        Path(args[1]).write_text(json.dumps(picked, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{len(picked)} lines")
    elif command == "lab":
        lab(args[0], args[1], tuple(float(f) for f in args[2].split(",")) if len(args) > 2 else (1.0, 1.25, 1.5),
            int(args[3]) if len(args) > 3 else 100)
    else:
        raise SystemExit(__doc__)
