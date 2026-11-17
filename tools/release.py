"""Build a release into dist/: barrens-voice-<version>.zip and manifest.json (`mise run build`).

The archive is what bv/install.py puts into <install>\\app\\<version>: companion/ (the code, without the
tests), addon/BarrensVoice, pyproject.toml, uv.lock, LICENSE, and Barrens Voice.exe when built (on Windows). The manifest tells the launcher's updater
what is there: the app's version, the strip protocol, the addon's version, the archive's name, size
and SHA-256 (`mise run sign` adds a signature).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
# the uv the installer ships and the updates bring (the manifest names it: an install with another fetches it)
UV_VERSION = "0.13.7"
UV_ZIP = f"https://github.com/astral-sh/uv/releases/download/{UV_VERSION}/uv-x86_64-pc-windows-msvc.zip"


def uv_entry() -> dict:
    """The uv of this release for the manifest: version, where its Windows build is, its published SHA-256."""
    import urllib.request
    request = urllib.request.Request(UV_ZIP + ".sha256", headers={"User-Agent": "barrens-voice-build"})
    with urllib.request.urlopen(request, timeout=60) as r:  # noqa: S310
        sha = r.read().decode().split()[0]
    return {"version": UV_VERSION, "url": UV_ZIP, "sha256": sha}
# only tracked files are packed (files()): what is left out of those - the tests and the source-run setup
SKIP_DIRS = {"tests"}
SKIP_FILES = {"requirements.txt", "BarrensVoice.cmd"}


def files() -> list[tuple[Path, str]]:
    """(source, name in the archive): only what git tracks, so nothing made on this machine slips in."""
    import subprocess
    tracked = subprocess.run(["git", "ls-files", "-z", "companion", "addon/BarrensVoice", "pyproject.toml", "uv.lock",
                              "LICENSE"], cwd=ROOT, capture_output=True, check=True).stdout.decode().split("\0")
    out = []
    for name in filter(None, tracked):
        parts = Path(name).parts
        if SKIP_DIRS & set(parts) or parts[-1] in SKIP_FILES:
            continue
        out.append((ROOT / name, name))
    return out


def versions() -> dict:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    toc = (ROOT / "addon" / "BarrensVoice" / "BarrensVoice.toc").read_text(encoding="utf-8")
    proto = re.search(r"^VERSION = (\d+)", (ROOT / "companion" / "bv" / "protocol.py").read_text(encoding="utf-8"), re.M)
    return {"version": project["version"], "addon": re.search(r"^## Version:\s*(\S+)", toc, re.M).group(1),
            "protocol": int(proto.group(1))}


def notes(version: str) -> str:
    """The release's notes: its CHANGELOG.md section (`## [<version>] - <date or Unreleased>`, Keep a Changelog),
    up to the next version or the link lines at the bottom."""
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    m = re.search(rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## |^\[[^\]\n]+\]: |\Z)", text, re.M | re.S)
    return (m.group(1).strip() if m else "") + "\n\nУстановка: скачайте `BarrensVoice-Setup.exe` и запустите его.\n"


def dictionary_revision() -> int:
    """The time of the last commit that changed Dictionary.lua - tools/dictionary_json.py's revision, so the
    online dictionary and the release's agree - or 0 outside git."""
    import subprocess

    from dictionary_json import revision
    try:
        return revision()
    except (OSError, subprocess.CalledProcessError, ValueError, SystemExit):
        return 0


def version_of(tag: str, base: str) -> str:
    """The release's version from its tag: "v0.4.0" -> "0.4.0", "v0.4.0-beta.5" -> "0.4.0b5" (a test build,
    older than 0.4.0 for the updater). The tag must name pyproject.toml's version."""
    m = re.fullmatch(r"v(\d+\.\d+\.\d+)(?:-beta\.(\d+))?", tag)
    if not m or m.group(1) != base:
        sys.exit(f"the tag {tag} and pyproject.toml's version {base} differ (tags: vX.Y.Z or vX.Y.Z-beta.N)")
    return f"{base}b{m.group(2)}" if m.group(2) else base


def build() -> Path:
    info = versions()
    base = info["version"]
    tag = os.environ.get("RELEASE_TAG", "")
    if tag:
        info["version"] = version_of(tag, base)
        if "b" not in info["version"] and "b" in info["addon"]:
            sys.exit(f"the release {tag} would carry a test build of the addon ({info['addon']}): give the addon its "
                     "release version in BarrensVoice.toc")
    DIST.mkdir(exist_ok=True)
    archive = DIST / f"barrens-voice-{info['version']}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        extra = [(DIST / "Barrens Voice.exe", "Barrens Voice.exe")] if (DIST / "Barrens Voice.exe").is_file() else []
        for source, name in sorted(files() + extra, key=lambda f: f[1]):   # the starter: built first on Windows
            info_ = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))   # a fixed time, not the checkout's
            info_.compress_type = zipfile.ZIP_DEFLATED
            data = source.read_bytes()
            if name == "pyproject.toml" and info["version"] != base:     # the build's own version, beta and all
                data = re.sub(rb'(?m)^version = "[^"]*"', f'version = "{info["version"]}"'.encode(), data, count=1)
            if name == "addon/BarrensVoice/Dictionary.lua":                # which default this is (the dictionary online)
                data = re.sub(rb"(?m)^D\.REVISION = \d+", f"D.REVISION = {dictionary_revision()}".encode(), data, count=1)
            z.writestr(info_, data)
    data = archive.read_bytes()
    manifest = {**info, "archive": archive.name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                "uv": uv_entry()}
    (DIST / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (DIST / "notes.md").write_text(notes(base), encoding="utf-8")
    print(f"{archive.name}: {len(data) / 1e6:.1f} MB; manifest: {manifest}")
    return archive


if __name__ == "__main__":
    build()
    sys.exit(0)
