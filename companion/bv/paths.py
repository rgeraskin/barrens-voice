"""Where Barrens Voice's code and data are (docs/update-strategy.md).

Installed, the code of a version is <install>\\app\\<version>\\companion, and <install>\\app\\current is a
junction to the version in use: the shortcut and the sign-in command go through it, an update points
it at the new version. The install's root carries the mark file INSTALL_MARK.

CODE_DIR  - the companion's folder, bv's parent: the code, BarrensVoice.pyw, the addon beside it
            (../addon/BarrensVoice).
DATA_DIR  - what the player's machine makes and keeps across versions: config.json, assignments.json,
            the voice bank, logs, tmp, models: <install>\\data.
CACHE_DIR - the model cache (hf, unless config.json's hf_home says another) and uv's: <install>\\cache.
Not installed (development, the folder BarrensVoice.cmd made) both are the companion's own folder, as
before the installer. BV_DATA, BV_CACHE and BV_STARTER override them (tests, odd setups).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

INSTALL_MARK = "barrens-voice.install"


def layout(code_dir: Path, env=os.environ) -> dict:
    """{"root": the install's folder or None, "data": ..., "cache": ..., "starter": the command line that
    starts the launcher, without its switches}."""
    code_dir = Path(code_dir)
    root = code_dir.parent.parent.parent              # <install>\app\<version>\companion
    root = root if (root / INSTALL_MARK).is_file() and code_dir.parent.parent.name == "app" else None
    data = Path(env.get("BV_DATA") or (root / "data" if root else code_dir))
    cache = Path(env.get("BV_CACHE") or (root / "cache" if root else data))
    if env.get("BV_STARTER"):
        start = env["BV_STARTER"]
    elif root:
        current = root / "app" / "current"
        start = f'"{current / ".venv" / "Scripts" / "pythonw.exe"}" "{current / "companion" / "BarrensVoice.pyw"}"'
    else:
        start = f'"{Path(sys.executable).with_name("pythonw.exe")}" "{code_dir / "BarrensVoice.pyw"}"'
    return {"root": root, "data": data, "cache": cache, "starter": start}


CODE_DIR = Path(__file__).resolve().parent.parent     # resolve(): through app\current, the real version
_LAYOUT = layout(CODE_DIR)
INSTALL_DIR: Path | None = _LAYOUT["root"]
DATA_DIR: Path = _LAYOUT["data"]
CACHE_DIR: Path = _LAYOUT["cache"]


def starter() -> str:
    """The command line that starts the launcher (without its switches)."""
    return _LAYOUT["starter"]
