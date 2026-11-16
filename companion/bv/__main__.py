"""Barrens Voice companion: reads the addon's strip off the WoW window and speaks each chat line.

Run: python -m bv  (config.json next to the bv folder is created on first run)
"""
from __future__ import annotations

import contextlib
import dataclasses
import json
import os
import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from . import protocol
from .paths import CACHE_DIR, DATA_DIR      # the data's folder, apart from the code's (bv/paths.py)

CONFIG_PATH = DATA_DIR / "config.json"
DEFAULT_CONFIG = {
    "_help": "rate -10..10, volume 0..100. exclude: voices left out (part of the name). "
             "gender_overrides: voices whose gender SAPI does not know. players: {\"Name\": \"part of a voice name\"}. "
             "stress: how each engine gets the dictionary's stress marks (plus, acute or strip). "
             "engine: f5 (race voices from the game client, on a DirectX 12 GPU) or sapi (Windows voices). "
             "voice_shifts: semitones of the extra copies of each race voice. players: also takes F5 voice ids (orc-male#60).",
    "engine": "f5",
    "rate": 0,
    "volume": 100,
    "max_queue": 8,
    "exclude": ["Irina Desktop", "Dmitry Online"],
    "gender_overrides": {"Aidar": "Male", "Eugene": "Male", "Baya": "Female", "Kseniya": "Female", "Xenia": "Female"},
    "players": {},
    "stress": {"rhvoice": "acute", "silero": "plus", "edge": "strip", "other": "strip"},
    "ruaccent": True,
    "restore_yo": True,
    "declension": True,
    "f5_margin": 1.25,
    "f5_tail": 0.5,
    # a take whose speech reaches its very end (about one in eight): "silence" - made again, a second
    # longer; "whisper" - made again only if Whisper does not hear the last word (1.5 GB of video memory)
    "f5_end_check": "silence",
    # slow voices drawn toward the bank's faster quarter (quantile) by this share, at most this many
    # times faster; each character's own tempo within this share either way (f5engine.line_seconds)
    "voice_pace_quantile": 0.25,
    "voice_pace_blend": 0.85,
    "voice_pace_limit": 1.8,
    "character_tempo": 0.08,
    # F5 only; 0 turns a part off. See bv/intonation.py.
    "question_intonation": {"yes_no_rise_st": 7, "yes_no_end_db": 8, "wh_peak_st": 6},
    "kind_gain_db": {"yell": 3, "whisper": -4},
    "voice_shifts": [-1.5, 1.5],
    "wow_dir": "",
    "game_dirs": {},              # {"forever": "...\\_forever_"}: the folders the launcher found
    "hf_home": "",
    "launch_wow": True,
    "game": "forever",            # or "retail"; --retail / --forever on the command line override it
    "launch_product": "WoWF",
    "launch_product_retail": "WoW",
    "battlenet_exe": "",
    "exit_with_wow": True,
    "spoken_notices": False,
    # a character's next line within this many seconds after their previous one was heard (or while
    # it still is) goes on without their name: one speech
    "same_speaker_gap": 5.0,
    "log_details": True,
    "log_keep_days": 90,
    # the game first (bv/share.py): ONNX threads few and sleeping, the companion's priority below normal
    "share_with_game": True,
    "onnx_threads": 2,
    "debug": False,
    "poll_interval": 0.05,
    "capture_height": 16,
    "window_capture": True,
}
MARKUP = re.compile(r"\|c[0-9a-fA-F]{8}|\|r|\|T.*?\|t|\|A.*?\|a")
LABELS = {"party": "группа", "raid": "рейд", "warning": "объявление", "instance": "подземелье",
          "say": "сказать", "yell": "крик", "whisper": "шёпот", "guild": "гильдия", "officer": "офицеры",
          "channels": "канал", "emote": "эмоция", "test": "тест",
          "notice": "программа"}


LOG_DIR = DATA_DIR / "logs"
_log_file = None
_log_day = None


_log_lock = threading.Lock()


def _write_log_file(line: str, now: datetime) -> None:
    """One line into logs/bv-YYYY-MM-DD.log (appended: one file a day, kept for later)."""
    global _log_file, _log_day
    with _log_lock:
        try:
            day = f"{now:%Y-%m-%d}"
            if day != _log_day:
                if _log_file is not None:
                    _log_file.close()
                LOG_DIR.mkdir(exist_ok=True)
                _log_file = open(LOG_DIR / f"bv-{day}.log", "a", encoding="utf-8", buffering=1)
                _log_day = day
            _log_file.write(line + "\n")
        except OSError:
            pass


def log(message: str, level: str | None = None) -> None:
    """To the console (the launcher reads it) and to logs/bv-YYYY-MM-DD.log, with its level (bv/logs.py)."""
    from .logs import level_of
    now = datetime.now()
    line = f"{now:%H:%M:%S} {level or level_of(message):<5} {message}"
    print(line, flush=True)
    _write_log_file(line, now)


class StderrToLog:
    """What the libraries write to stderr (warnings of the libraries, errors outside the
    program's own logging) goes to the console as before and to the log file too, a line at a time
    with the time. A progress bar redraws its line with "\\r": only the finished line is kept."""

    def __init__(self, console):
        self.console, self.pending = console, ""

    def write(self, text: str) -> int:
        launched = bool(os.environ.get(LAUNCHED))      # under the launcher: lines in the log's form only
        if not launched:
            try:
                self.console.write(text)
            except (OSError, ValueError):
                pass
        self.pending += text
        while "\n" in self.pending:
            line, self.pending = self.pending.split("\n", 1)
            line = line.split("\r")[-1].rstrip()
            if line:
                if launched:
                    log(f"[stderr] {line}", "DEBUG")
                else:
                    now = datetime.now()
                    _write_log_file(f"{now:%H:%M:%S} DEBUG [stderr] {line}", now)
        if "\r" in self.pending:                       # a bar redrawing itself: only its last state counts
            self.pending = self.pending.rsplit("\r", 1)[-1]
        return len(text)

    def flush(self) -> None:
        try:
            self.console.flush()
        except (OSError, ValueError):
            pass

    def __getattr__(self, name):                        # isatty, encoding, fileno... as the console has them
        return getattr(self.console, name)


def prune_logs(keep_days: int) -> None:
    """Delete daily logs older than `keep_days` (0: keep them all)."""
    if keep_days <= 0 or not LOG_DIR.is_dir():
        return
    cutoff = datetime.now().timestamp() - keep_days * 86400
    for path in LOG_DIR.glob("bv-*.log"):
        if path.stat().st_mtime < cutoff:
            path.unlink(missing_ok=True)


def load_config() -> dict:
    config = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        config.update(saved)
        if any(key not in saved for key in DEFAULT_CONFIG):   # new settings: write them in
            CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2), encoding="utf-8")
    return config


MODELS_READY = DATA_DIR / ".models_ready"
# the launcher (bv.launcher): what the companion does, and its word to stop
STATE_FILE = DATA_DIR / "tmp" / "state.json"
STOP_FILE = DATA_DIR / "tmp" / "stop"
RESTART = 3               # exit code: start me again (online) - the launcher does it
ALREADY = 4               # exit code: another companion runs
LAUNCHED = "BV_LAUNCHER"  # set in the environment of a companion the launcher started


def single_instance() -> bool:
    """True for the only companion on this Windows session (a named mutex, freed when the process
    ends however it ends); False when another one already runs - two would read the same strip
    and speak every line twice."""
    import ctypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    global _mutex
    _mutex = kernel32.CreateMutexW(None, False, "Local\\BarrensVoiceCompanion")
    return ctypes.get_last_error() != 183          # ERROR_ALREADY_EXISTS


_mutex = None


def install_crash_logging() -> None:
    """Uncaught errors - in the main thread or any other - go to the log too, not only the console."""
    import threading
    import traceback

    def report(kind, exc_type, exc, tb):
        log(f"ОШИБКА ({kind}): {exc_type.__name__}: {exc}")
        for chunk in traceback.format_exception(exc_type, exc, tb):
            for line in chunk.rstrip().splitlines():
                log("  " + line)

    sys.excepthook = lambda t, e, tb: report("программа", t, e, tb)
    threading.excepthook = lambda a: report(f"поток {a.thread.name if a.thread else '?'}", a.exc_type,
                                            a.exc_value, a.exc_traceback)


def offline_models() -> bool:
    """After the models were loaded once (F5, Vocos, RUAccent in the Hugging Face cache), never ask
    the hub again: no update checks at start, no "unauthenticated requests" warnings, and nothing
    breaks if the site is down or a model is taken away. Must run before huggingface_hub loads."""
    if MODELS_READY.exists():
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        return True
    return False


def restart_online(log) -> None:
    """A model missing from the cache in offline mode: forget the mark and start again online (under
    the launcher: exit with RESTART, it starts the companion again - so it keeps its process)."""
    MODELS_READY.unlink(missing_ok=True)
    log("в кэше моделей чего-то не хватает — перезапускаюсь с доступом к сети")
    if os.environ.get(LAUNCHED):
        os._exit(RESTART)          # from any thread (engines.on_error runs on its own)
    os.execv(sys.executable, [sys.executable, "-m", "bv"] + sys.argv[1:])


def describe_place(place) -> str:
    x, y, w, h, sw, sh = place
    where = "верх" if y == 0 and w == sw else "низ" if y + h == sh and w == sw else "своё место"
    return f"{where}, x {x}, y {y}, ширина {w} (экран {sw}×{sh})"


def fetch_models(config: dict) -> int:
    """Everything the race voices need from the network, downloaded now - BarrensVoice.cmd runs this
    right after installing, so the first start neither waits for ~3 GB nor needs the network: F5 in
    ONNX and its vocabulary, Whisper (it builds the voice bank from the game's files), RUAccent.
    Models already in the cache are not downloaded again."""
    os.environ.setdefault("HF_HUB_VERBOSITY", "error")     # no "unauthenticated requests" notice; bars stay
    from huggingface_hub import hf_hub_download

    from . import f5engine, whisper_onnx
    from .text import Accentor
    try:
        log("модели: голоса рас (~0,8 ГБ) ...")
        if f5engine.model_dir(config, DATA_DIR) is None:
            f5engine.fetch_models(config, log)
        hf_hub_download(f5engine.MODEL_REPO, f5engine.VOCAB_FILE)
        log("модели: распознавание речи для банка голосов (~1,5 ГБ) ...")
        for name in whisper_onnx.FILES:
            hf_hub_download(whisper_onnx.REPO, name)
        log("модели: ударения (~0,7 ГБ) ...")
        Accentor(log, True).load()
    except Exception as e:  # noqa: BLE001 - the first start tries again
        log(f"модели не скачались: {e} — компаньон докачает их при первом запуске")
        return 1
    log("модели скачаны")
    return 0


def main() -> int:
    if sys.platform != "win32":
        print("Windows only")
        return 1
    offline = offline_models() if "--fetch-models" not in sys.argv else False
    install_crash_logging()
    if not isinstance(sys.stderr, StderrToLog):
        sys.stderr = StderrToLog(sys.stderr)
    from .speech import Speaker
    from .capture import Capturer
    from .window import make_dpi_aware

    make_dpi_aware()

    config = load_config()
    for game in ("retail", "forever"):                # BarrensVoice-Retail.cmd: the same companion, the other game
        if f"--{game}" in sys.argv:
            config["game"] = game
    # one Hugging Face cache for every model (F5, Vocos, RUAccent, Whisper): hf_home in config.json,
    # else the hf folder next to the program - before anything of Hugging Face is imported
    os.environ["HF_HOME"] = config.get("hf_home") or str(CACHE_DIR / "hf")
    # transformers (Whisper's features and tokenizer, RUAccent) says at import that it found no
    # PyTorch - on purpose since 0.4.0: only its errors are worth the log
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
    # the game first: ONNX Runtime's threads few and sleeping, the companion below normal (bv/share.py)
    from . import share
    if config.get("share_with_game", True):
        share.limit_onnx(int(config.get("onnx_threads", 2)))
    if "--selftest" in sys.argv:
        from .speech import selftest
        selftest(config, log)
        return 0
    if "--selftest-f5" in sys.argv:
        from .f5engine import selftest as f5_selftest
        return f5_selftest(config, log, DATA_DIR)
    if "--fetch-models" in sys.argv:
        return fetch_models(config)
    log("=" * 60)
    if not single_instance():
        log("компаньон уже запущен — второй не нужен, выхожу")
        return ALREADY
    STOP_FILE.unlink(missing_ok=True)
    if config.get("share_with_game", True):
        share.lower_priority(log)
    from . import state
    from .dictionary import game_of
    state.init(STATE_FILE, phase="starting", game=game_of(config))
    # the launcher says «компаньон запущен (игра)» itself: here only the details, for the full log
    log(f"компаньон стартует; игра: {'WoW (ритейл)' if game_of(config) == 'retail' else 'WoW Forever'}; "
        f"настройки: {CONFIG_PATH}", "DEBUG")
    prune_logs(config["log_keep_days"])
    from . import launch
    from .status import Beat, SeenLines
    from .voicelist import find_addon, missing_addon
    problem = missing_addon(config)
    if problem:                   # nothing would ever reach the companion: say so and stop
        log("ОШИБКА: " + problem)
        state.report(phase="error", error=problem)
        return 1
    # "the companion is running", for the addon at login (status.py): from now on, before the game
    # is launched and while the models load
    # asked before the first beat: is the player already in the world, the addon past its check? (reloadhint)
    from . import reloadhint
    needs_reload = reloadhint.needed(config, find_addon(config))
    beat = Beat(find_addon(config), log)
    beat.start()
    if needs_reload:
        log("если окно чата не прячется — сделайте в игре /reload: аддон узнаёт о компаньоне при входе и /reload")
        state.report(reload_hint=True)
    import atexit
    atexit.register(beat.stop)        # any end - the game closed, a crash, the launcher's stop - but a kill
    seen_lines = SeenLines(DATA_DIR / "tmp" / "seen_lines.txt")
    # --launch / --no-launch: the launcher's Play and its start for a game already running
    want_launch = "--launch" in sys.argv or (config["launch_wow"] and "--no-launch" not in sys.argv)
    if want_launch and not launch.wow_running():
        # the race voices come from the client's files: (re)made before the game, after an update
        from .f5engine import prepare_voices
        prepare_voices(config, DATA_DIR, log)
        launch.launch(config, log)   # the game starts while the voices load
    from .dictionary import Dictionary
    dictionary = Dictionary(config, log, find_addon(config))
    dictionary.refresh()
    dictionary_checked = time.monotonic()
    from .text import Accentor, plain
    from .unmask import unmask
    from . import yo
    restore_yo = yo.restore if config.get("restore_yo", True) else (lambda t: t)
    if config.get("restore_yo", True):
        log(f"словарь «ё»: {sum(1 for k in yo.table() if k[:1].islower())} форм слов")
    accentor = Accentor(log, config.get("ruaccent", True))
    log("загружаю RUAccent ..." + (" (модели из кэша, без сети)" if offline else ""))
    try:
        accentor.load()
    except Exception as e:  # noqa: BLE001 - offline with a model missing: go online once
        if offline:
            log(f"RUAccent: {e}")
            restart_online(log)
        raise
    from .morph import Inflector, strip_marks
    inflector = Inflector(log, config.get("declension", True))
    inflector.load()
    from .audio import Player
    player = Player(config["max_queue"], DATA_DIR / "tmp", log=log)
    player.start()
    sapi = Speaker(config, log, accentor, player)
    sapi.start()
    sapi.ready.wait(120)
    log(f"голосов Windows: {len(sapi.all_voices)} (включено {len(sapi.voices)})")
    from . import voicelist
    voicelist.write(config, sapi.all_voices, sapi.default_off, log)
    from .engines import Engines
    engines = Engines(config, log, DATA_DIR, sapi, accentor, player)
    engines.on_ready = lambda: MODELS_READY.touch()
    engines.on_error = (lambda error: restart_online(log)) if offline else None
    # The race voices load while the game starts, not when its first chat line comes - unless the
    # addon was last set to Windows voices (then F5 is loaded only if the addon asks for it).
    from .dictionary import saved_voices
    if "--f5" in sys.argv or (saved_voices(config) or config["engine"]) == "f5":
        engines.want("f5")

    seen = None
    linked = False
    window, window_checked = None, 0.0
    first_check = True
    misses = 0
    damaged_since = None      # a strip in view whose frames do not check out, since when
    last_speaker = None       # (kind, sender, channel) of the last chat line passed on
    damaged_told = False
    wow_seen, wow_gone_since, wow_checked = False, None, 0.0
    unknown_kinds: set[str] = set()
    capturer = Capturer(config, log)
    from . import locate
    place = locate.saved_place(config)
    if place:                     # where the addon last put the strip; its settings frame says it again
        capturer.set_place(place)
        log("полоска (по сохранённым настройкам аддона): " + describe_place(place))
    absent_since, searched = None, 0.0
    state.report(phase="running")
    with contextlib.nullcontext():
        while True:
            now = time.monotonic()
            if now - dictionary_checked > 2:
                dictionary.refresh()               # a changed Dictionary.lua works within seconds
                dictionary_checked = now
                if STOP_FILE.exists():             # the launcher's "stop" (its window closed, «Выход»)
                    STOP_FILE.unlink(missing_ok=True)
                    log("остановлен лаунчером")
                    state.report(phase="stopped")
                    return 0
            if config["exit_with_wow"] and now - wow_checked > 2:
                wow_checked = now
                if launch.wow_running():
                    wow_seen, wow_gone_since = True, None
                elif wow_seen:
                    wow_gone_since = wow_gone_since or now
                    if now - wow_gone_since > 10:
                        log("игра закрыта — выхожу")
                        state.report(phase="game_closed")
                        return 0
            if window is None or now - window_checked > 2:
                found = capturer.find()
                if found != window or first_check:
                    log(f"окно WoW: {found[1]}" if found else "окно игры не найдено или свёрнуто — жду")
                    state.report(window=bool(found))
                window, window_checked, first_check = found, now, False
            if window is None:
                time.sleep(1)
                continue
            try:
                grabbed = capturer.grab()
            except Exception as e:  # noqa: BLE001 - window moved or closed between checks
                log(f"снимок не удался: {e}")
                window = None
                continue
            if grabbed is None:
                time.sleep(config["poll_interval"])
                continue
            frame = protocol.decode(protocol.Image(*grabbed))
            if frame is None and protocol.last_failure == "absent":
                # no strip where it was said to be: look over the whole window, every 5 s (~0.3 s of work)
                absent_since = absent_since or time.monotonic()
                if time.monotonic() - absent_since > 2 and time.monotonic() - searched > 5:
                    searched = time.monotonic()
                    whole = capturer.grab_full()
                    # rows enough for a narrow strip: the addon makes it thicker so a long line fits
                    hit = locate.find(*whole, width_hint=capturer.rect[2],
                                      capture_height=max(config["capture_height"], 64)) if whole else None
                    if hit and hit[:4] != capturer.rect:
                        capturer.use(hit[:4])
                        log(f"полоска найдена в другом месте: x {hit[0]}, y {hit[1]}, ширина {hit[2]}")
            elif frame is not None:
                absent_since = None
            if frame is None:
                misses += 1
                if protocol.last_failure == "damaged":
                    now = time.monotonic()
                    damaged_since = damaged_since or now
                    if not damaged_told and now - damaged_since > 1.0:
                        log("полоска видна, но кадры не читаются: её что-то перекрывает (миникарта, окно другого "
                            "аддона?) или настройки изображения искажают цвета")
                        damaged_told = True
                        state.report(damaged=True)
                else:
                    damaged_since = None
                    if damaged_told:             # gone, not covered: its own state now (minimized, hidden UI)
                        damaged_told = False
                        state.report(damaged=False)
                if linked and misses == int(5 / config["poll_interval"]):
                    log("полоска аддона пропала (выключен, свёрнут или скрыт интерфейс?)")
                    linked = False
                    state.report(linked=False)
            else:
                misses = 0
                damaged_since = None
                if damaged_told:                 # readable again: a later cover is told again
                    damaged_told = False
                    log("полоска снова читается")
                    state.report(damaged=False)
                if not linked:
                    log("связь с аддоном есть")
                    log(f"    ячейка полоски: {frame.cell} px")
                    linked = True
                    state.report(linked=True)
                if frame.seq != seen:
                    first = seen is None       # what was up before we started: not news
                    seen = frame.seq
                    line = protocol.parse(frame.payload)
                    if line and line.off is not None:
                        sapi.set_disabled({n for n in line.off.split("|") if n})
                    if line and line.voice:
                        engines.want(line.voice)
                    if line and line.kind == "control":
                        # settings: applied above; and where the strip is (or is about to move)
                        place = locate.parse_place(line.options.get("strip", ""))
                        if place and place != capturer.place:
                            capturer.set_place(place)
                            log("полоска: " + describe_place(place))
                    elif line and line.kind == "dict":
                        dictionary.receive(line.options, line.text)  # state, not speech: even if first
                    elif line and line.kind == "stop":
                        if not first:
                            engines.stop()
                            log("стоп: замолкаю")
                    elif line and line.kind == "pause":            # state: even if first
                        if player.pause():
                            log("CatQuest говорит: чат на паузе")
                    elif line and line.kind == "resume":
                        if player.resume():
                            log("CatQuest замолчал: чат продолжает (прерванная строка — сначала)")
                    elif line and line.kind == "reset" and not first:
                        engines.reset_assignments()
                    elif line and line.kind == "open":
                        if not first:                          # a click in the addon's settings
                            from .links import open_link
                            open_link(line.text, log)
                    elif line and line.kind == "copy":
                        if not first:
                            from .links import copy_link
                            copy_link(line.text, log)
                    elif line and line.kind == "diag" and not first:
                        log(f"[диагностика аддона] {line.text}")
                    elif line and line.kind not in LABELS:
                        # a service line of a newer addon: never read aloud what is not chat
                        if line.kind not in unknown_kinds:
                            unknown_kinds.add(line.kind)
                            log(f"строки типа «{line.kind}» не озвучиваю (аддон новее программы?)")
                    elif line and line.text and not first and seen_lines.seen(line.options.get("id", "")):
                        # a line the addon sent again: this one was read already
                        log(f"строка {line.options.get('id')} уже прочитана — пропускаю повтор")
                    elif line and line.text and not first:
                        speaker_key = (line.kind, line.sender, line.channel)
                        continuing = (speaker_key == last_speaker
                                      and engines.quiet_for() <= config["same_speaker_gap"])
                        last_speaker = speaker_key
                        name, text, droppable = protocol.split_name(line.text)
                        if continuing and droppable:
                            name, text = "", text.lstrip()
                        text = unmask(MARKUP.sub("", text))   # "xyйня", "п0шел", "бл*ть"
                        # the dictionary's words, then its regexes (whose own patterns want plain
                        # text): each replacement declined after its preposition when that is on;
                        # the name is left as it is
                        text = dictionary.apply_words(text)
                        text = inflector.apply(text) if line.declension else strip_marks(text)
                        text = dictionary.apply(text, mark=line.declension)
                        text = inflector.apply(text) if line.declension else strip_marks(text)
                        text = protocol.with_name(name, restore_yo(plain(text)))   # «ждем» -> «ждём»; not the name
                        line = dataclasses.replace(line, text=text)
                        speaker = engines.for_line(line)
                        label = LABELS.get(line.kind, line.kind) + (f" {line.channel}" if line.channel else "")
                        log(f"[{label}] {line.sender} ({line.race or '?'}"
                            f"{', м' if line.sex == '2' else ', ж' if line.sex == '3' else ''})"
                            f" → {speaker.describe(line)}: {text}")
                        if config["log_details"] and line.raw and line.raw != text:
                            log(f"    исходно:   {line.raw}")
                        speaker.say(line)
            time.sleep(config["poll_interval"])


if __name__ == "__main__":
    sys.exit(main())
