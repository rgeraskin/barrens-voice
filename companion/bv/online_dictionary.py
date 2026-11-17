"""The dictionary online: a fresher default dictionary from GitHub, without an addon update.

CI builds `dictionary.json` from the addon's Dictionary.lua after the tests pass on master (tools/
dictionary_json.py) and signs it with the release key; it lives in the branch `dictionary`. The companion
fetches it at start and hourly, takes it only when its signature holds, its format is the one it reads
(FORMAT: raised when the file's shape or the dictionary's syntax changes - an older companion then keeps
its last dictionary) and its regexes compile and run fast (they are run by us, on every chat line), and keeps the last good one in the data folder for starts without the network. It is the default
when it is newer than the addon's own (`revision`: the time of the last commit that changed Dictionary.lua,
which tools/release.py writes into a release's Dictionary.lua too): the companion applies it at once, and
writes it into the addon as DictionaryOnline.lua so the dictionary window shows it after the next /reload.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path

from . import update

URL = "https://raw.githubusercontent.com/rgeraskin/barrens-voice/dictionary/"
FILE = "dictionary.json"
FORMAT = 1
CHECK_EVERY = 3600.0          # seconds between fetches while the companion runs
MAX_PATTERN = 400             # characters: a longer regex is not one we write
CHECK_TIMEOUT = 15.0          # seconds for all the regexes on the probe strings, in a process of their own
# what every regex runs over in the check: long runs that make a backtracking pattern explode
PROBES = ["а" * 4000 + "!", "a" * 4000 + "!", "1" * 4000 + "x", " ".join(["слово"] * 800), "ж" * 2000 + " 5к 2дд"]
PROBE = r"""
import json, re, sys
patterns, probes = json.loads(sys.stdin.read())
for p in patterns:
    rx = re.compile(p, re.IGNORECASE)
    for s in probes:
        rx.sub("", s)
print("ok")
"""


def patterns(text: str) -> list[str]:
    """The regexes of a dictionary text ("~pattern=replacement" lines)."""
    return [line.strip()[1:].rsplit("=", 1)[0].strip() for line in text.splitlines()
            if line.strip().startswith("~") and "=" in line]


def regexes_ok(text: str, timeout: float = CHECK_TIMEOUT) -> str | None:
    """None when every regex compiles, is of a sane length and runs fast over PROBES (in a separate Python,
    killed at `timeout`: a runaway pattern cannot hang the companion); else what is wrong."""
    import re
    found = patterns(text)
    for p in found:
        if len(p) > MAX_PATTERN:
            return f"регулярка длиннее {MAX_PATTERN} символов"
        try:
            re.compile(p, re.IGNORECASE)
        except re.error as e:
            return f"регулярка «{p[:60]}» с ошибкой: {e}"
    try:
        done = subprocess.run([sys.executable, "-I", "-c", PROBE], input=json.dumps([found, PROBES]),
                              capture_output=True, text=True, encoding="utf-8", timeout=timeout,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        return f"регулярки слишком медленные (дольше {timeout:g} с на проверочных строках)"
    if done.stdout.strip() != "ok":
        return f"проверка регулярок не прошла: {done.stderr.strip()[-200:]}"
    return None


def load(raw: bytes, signature: str, public: str = update.PUBLIC_KEY, check=regexes_ok) -> tuple[dict | None, str]:
    """(the dictionary, "") when `raw` is one this companion may use, else (None, why not)."""
    if not update.verify(raw, signature, public):
        return None, "подпись не сходится"
    try:
        data = json.loads(raw)
    except ValueError:
        return None, "не JSON"
    if data.get("format") != FORMAT:
        return None, f"формат {data.get('format')}, а программа читает {FORMAT}"
    if not isinstance(data.get("text"), str) or not isinstance(data.get("renamed", {}), dict) \
            or not isinstance(data.get("revision"), int):
        return None, "описание без текста или ревизии"
    why = check(data["text"])
    if why:
        return None, why
    return data, ""


def lua(data: dict) -> str:
    """DictionaryOnline.lua for the addon: the default as a Lua long string at a level its text does not close."""
    level = 0
    while ("]" + "=" * level + "]") in data["text"]:
        level += 1
    eq = "=" * level

    def q(s: str) -> str:
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'
    renamed = "".join(f"\n        [{q(k)}] = {q(v)}," for k, v in sorted(data.get("renamed", {}).items()))
    return ("-- Written by the Barrens Voice program: the default dictionary from GitHub when it is newer than the\n"
            "-- addon's own (Dictionary.lua uses the newer).\n"
            "BarrensVoiceDictionaryOnline = {\n"
            f"    revision = {int(data['revision'])},\n"
            f"    renamed = {{{renamed}\n    }},\n"
            f"    text = [{eq}[\n{data['text']}]{eq}],\n"
            "}\n")


class Online:
    """The dictionary online for one companion: the cached copy, the hourly fetch on a thread of its own, and
    `take()` for the main loop - the newer dictionary when one came (applied there, between chat lines)."""

    def __init__(self, folder: Path, log, fetch=update.get, public: str = update.PUBLIC_KEY, check=regexes_ok):
        self.folder, self.log = Path(folder), log
        self.fetch, self.public, self.check = fetch, public, check
        self.current: dict | None = None
        self.pending: dict | None = None
        self.lock = threading.Lock()

    def cached(self) -> dict | None:
        """The last good dictionary kept in the data folder (checked again: the folder is the player's)."""
        try:
            raw = (self.folder / FILE).read_bytes()
            sig = (self.folder / (FILE + ".sig")).read_text(encoding="ascii")
        except OSError:
            return None
        data, _ = load(raw, sig, self.public, self.check)
        self.current = data
        return data

    def fetch_once(self) -> dict | None:
        """Fetch and check the published dictionary; the newer one is kept and returned (also to `take`)."""
        try:
            raw = self.fetch(URL + FILE)
            sig = self.fetch(URL + FILE + ".sig").decode("ascii", "replace")
        except Exception as e:  # noqa: BLE001 - offline, GitHub down: the next time
            self.log(f"словарь онлайн: не скачался ({e})")
            return None
        data, why = load(raw, sig, self.public, self.check)
        if data is None:
            self.log(f"словарь онлайн не принят: {why}")
            return None
        if self.current and data["revision"] <= self.current["revision"]:
            return None
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder / FILE).write_bytes(raw)
        (self.folder / (FILE + ".sig")).write_text(sig, encoding="ascii")
        with self.lock:
            self.current = self.pending = data
        return data

    def take(self) -> dict | None:
        with self.lock:
            data, self.pending = self.pending, None
        return data

    def start(self, every: float = CHECK_EVERY) -> threading.Thread:
        def loop():
            import time
            while True:
                self.fetch_once()
                time.sleep(every)
        thread = threading.Thread(target=loop, daemon=True, name="dictionary-online")
        thread.start()
        return thread


def write_addon(addon: Path | None, data: dict, log) -> bool:
    """DictionaryOnline.lua in the addon's folder (only when it changes); whether it was written."""
    if addon is None or not addon.is_dir():
        return False
    path = addon / "DictionaryOnline.lua"
    text = lua(data)
    try:
        if path.exists() and path.read_text(encoding="utf-8") == text:
            return False
        path.write_text(text, encoding="utf-8")
    except OSError as e:
        log(f"словарь онлайн: не записан в аддон ({e})")
        return False
    return True
