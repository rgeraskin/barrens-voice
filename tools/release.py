"""Build a release into dist/: barrens-voice-<version>.zip and manifest.json (`mise run build`).

The archive is what bv/install.py puts into <install>\\app\\<version>: companion/ (the code, without the
tests), addon/BarrensVoice, pyproject.toml, uv.lock, LICENSE. The manifest tells the launcher's updater
what is there: the app's version, the strip protocol, the addon's version, the archive's name, size
and SHA-256 (`mise run sign` adds a signature).
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
SKIP_DIRS = {"__pycache__", "tests", ".venv", "tmp", "logs", "voices", "voices-retail", "models", "hf", "f5test"}
SKIP_FILES = {"config.json", "assignments.json", ".models_ready", "requirements.txt", "BarrensVoice.cmd", ".DS_Store"}


def files() -> list[tuple[Path, str]]:
    """(source, name in the archive): only what git tracks, so nothing made on this machine slips in."""
    import subprocess
    tracked = subprocess.run(["git", "ls-files", "-z", "companion", "addon/BarrensVoice", "pyproject.toml", "uv.lock",
                              "LICENSE"], cwd=ROOT, capture_output=True, check=True).stdout.decode().split("\0")
    out = []
    for name in filter(None, tracked):
        parts = Path(name).parts
        if SKIP_DIRS & set(parts) or parts[-1] in SKIP_FILES or parts[-1].startswith("._"):
            continue
        out.append((ROOT / name, name))
    return out


def versions() -> dict:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    toc = (ROOT / "addon" / "BarrensVoice" / "BarrensVoice.toc").read_text(encoding="utf-8")
    proto = re.search(r"^VERSION = (\d+)", (ROOT / "companion" / "bv" / "protocol.py").read_text(encoding="utf-8"), re.M)
    return {"version": project["version"], "addon": re.search(r"^## Version:\s*(\S+)", toc, re.M).group(1),
            "protocol": int(proto.group(1))}


def build() -> Path:
    info = versions()
    DIST.mkdir(exist_ok=True)
    archive = DIST / f"barrens-voice-{info['version']}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for source, name in sorted(files(), key=lambda f: f[1]):
            info_ = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))   # the same bytes from the same tree
            info_.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info_, source.read_bytes())
    data = archive.read_bytes()
    manifest = {**info, "archive": archive.name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    (DIST / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{archive.name}: {len(data) / 1e6:.1f} MB; manifest: {manifest}")
    return archive


if __name__ == "__main__":
    build()
    sys.exit(0)
