"""Where Barrens Voice's code and data are (docs/update-strategy.md).

CODE_DIR - the companion's folder, bv's parent: the code, BarrensVoice.pyw, the addon beside it
    (../addon/BarrensVoice). Installed, it is <install>\\app\\<version>\\companion.
DATA_DIR - what the player's machine makes and keeps across versions: config.json, assignments.json,
    the voice bank, logs, tmp, models. BV_DATA (the installer's <install>\\data, set by its starter);
    without it the companion's own folder, as before the installer and in development.
CACHE_DIR - the model cache (hf), unless config.json's hf_home says another: BV_CACHE (<install>\\cache)
    or DATA_DIR.
STARTER - how Windows starts the launcher at sign-in: BV_STARTER (the installed starter, which picks
    the current version), else this version's own BarrensVoice.pyw.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("BV_DATA") or CODE_DIR)
CACHE_DIR = Path(os.environ.get("BV_CACHE") or DATA_DIR)


def starter() -> str:
    """The command line that starts the launcher (without its switches)."""
    if os.environ.get("BV_STARTER"):
        return os.environ["BV_STARTER"]
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    return f'"{pythonw}" "{CODE_DIR / "BarrensVoice.pyw"}"'
