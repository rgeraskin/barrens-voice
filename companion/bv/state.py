"""What the companion is doing, for the launcher: tmp/state.json, rewritten whenever it changes.

The launcher shows it in its «Состояние» block - the race voices loading or ready, the link with
the addon, why the companion stopped. The companion's log lines go to the launcher as they are (its
stdout); this file holds the state those lines tell about, so the launcher never parses them.
Nothing is written until `init` is called (the companion's main does, in the console too): the tests and
the selftests write no file.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

_lock = threading.Lock()
_path: Path | None = None
_state: dict = {}


def init(path: Path, **fields) -> None:
    """Start a fresh state file for this run of the companion."""
    global _path, _state
    with _lock:
        _path, _state = Path(path), {"pid": os.getpid(), "started": time.time()}
    report(**fields)


def report(**fields) -> None:
    """Change some fields and write the file (through a temporary one: the launcher never reads half)."""
    with _lock:
        if _path is None:
            return
        _state.update(fields)
        text = json.dumps(_state, ensure_ascii=False)
        tmp = _path.with_suffix(".tmp")
        try:
            _path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, _path)
        except OSError:
            pass


def read(path: Path) -> dict:
    """The state as the companion last wrote it; {} if there is none (yet)."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
