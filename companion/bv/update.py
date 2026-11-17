"""Updates of an installed Barrens Voice from GitHub Releases (docs/update-strategy.md).

A release carries barrens-voice-<version>.zip, manifest.json (the app's, addon's and protocol's
versions, the archive's name, size and SHA-256) and manifest.json.sig (ed25519, tools/sign.py). The
updater trusts a manifest only when it verifies with PUBLIC_KEY, and an archive only when it matches
the manifest; then bv.install puts the version beside the current one (uv builds its environment
from its uv.lock) and app\\current is pointed at it when the game is not running. If the new version's
companion fails right at its start twice, the launcher points app\\current back (see `record_start`).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import urllib.request
from pathlib import Path

from . import install

REPO = "rgeraskin/barrens-voice"
PUBLIC_KEY = "6X3H4Ucf9JQriY67zjH+PABhyztH1VJyWXvuRMPOw3M="
# BV_UPDATE_BASE: another place of the latest release (a test: file:///E:/release/) - signed all the same
STABLE = os.environ.get("BV_UPDATE_BASE") or f"https://github.com/{REPO}/releases/latest/download/"
RELEASES = f"https://api.github.com/repos/{REPO}/releases?per_page=10"
AGENT = "BarrensVoice-launcher"
EARLY = 60.0          # seconds: a companion ending with an error sooner than this after its start "failed to start"


def get(url: str, timeout: float = 15.0) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:   # noqa: S310 - https to GitHub only
        return response.read()


def verify(manifest: bytes, signature: str, public: str = PUBLIC_KEY) -> bool:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(public)).verify(base64.b64decode(signature.strip()), manifest)
        return True
    except (InvalidSignature, ValueError):
        return False


def signed_manifest(base: str, fetch=get) -> dict | None:
    """The manifest at `base` if its signature holds, with "base": where its archive is."""
    raw = fetch(base + "manifest.json")
    if not verify(raw, fetch(base + "manifest.json.sig").decode("ascii", "replace")):
        return None
    return {**json.loads(raw), "base": base}


def latest(channel: str = "stable", fetch=get) -> dict | None:
    """The newest signed release of the channel: "stable" (the latest release) or "beta" (pre-releases too)."""
    if channel != "beta":
        return signed_manifest(STABLE, fetch)
    for release in json.loads(fetch(RELEASES)):
        if release.get("draft"):
            continue
        names = {a.get("name") for a in release.get("assets", [])}
        if {"manifest.json", "manifest.json.sig"} <= names:
            return signed_manifest(f"https://github.com/{REPO}/releases/download/{release['tag_name']}/", fetch)
    return None


def newer(candidate: str, current: str) -> bool:
    return install.version_key(candidate) > install.version_key(current)


def download(manifest: dict, folder: Path, progress=None, fetch_stream=None) -> Path:
    """The release archive into `folder`, checked against the manifest's size and SHA-256."""
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / manifest["archive"]
    part = target.with_suffix(".part")
    digest, size = hashlib.sha256(), 0
    request = urllib.request.Request(manifest["base"] + manifest["archive"], headers={"User-Agent": AGENT})
    with (fetch_stream or urllib.request.urlopen)(request, timeout=30) as response, open(part, "wb") as out:  # noqa: S310
        while chunk := response.read(1 << 16):
            out.write(chunk)
            digest.update(chunk)
            size += len(chunk)
            if progress:
                progress(size, manifest.get("size") or 0)
    if size != manifest.get("size") or digest.hexdigest() != manifest.get("sha256"):
        part.unlink(missing_ok=True)
        raise ValueError("архив обновления не совпал с подписанным описанием выпуска — не ставлю")
    part.replace(target)
    return target


def uv_version(uv: Path) -> str | None:
    """The version of an uv.exe («uv 0.13.7 (…)» -> "0.13.7"); None when it does not run."""
    import subprocess
    try:
        out = subprocess.run([str(uv), "--version"], capture_output=True, text=True, timeout=30,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.split()
        return out[1] if len(out) > 1 else None
    except (OSError, subprocess.SubprocessError):
        return None


def release_uv(root: Path, manifest: dict, log=print, fetch=get) -> Path:
    """The uv the release names (manifest "uv"): the installed uv.exe when it is that version, else that
    one downloaded, checked against the signed manifest's SHA-256 and unpacked beside as uv.new.exe."""
    import io
    import zipfile
    want, current = manifest.get("uv"), root / "uv.exe"
    if not want or uv_version(current) == want.get("version"):
        return current
    log(f"uv {want['version']} ...")
    data = fetch(want["url"])
    if hashlib.sha256(data).hexdigest() != want.get("sha256"):
        raise ValueError("uv не совпал с подписанным описанием выпуска — не ставлю")
    fresh = root / "uv.new.exe"
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        fresh.write_bytes(z.read("uv.exe"))
    return fresh


def prepare(root: Path, archive: Path, log=print, manifest: dict | None = None) -> str:
    """The version unpacked beside the current one and its environment built (with the uv the release names,
    which then replaces the installed one); not made current yet."""
    version, folder = install.unpack(archive, root)
    uv = release_uv(root, manifest or {}, log)
    install.build(root, folder, install.runtime_of(root), uv, log)
    if uv.name == "uv.new.exe":
        os.replace(uv, root / "uv.exe")
    return version


def state_path(root: Path) -> Path:
    return root / "data" / "tmp" / "update.json"


def apply(root: Path, version: str) -> None:
    """app\\current -> `version`, remembering the one before, to go back to if this one fails to start."""
    previous = install.current_version(root)
    install.point_current(root, root / "app" / version)
    path = state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": version, "previous": previous, "fails": 0}), encoding="utf-8")


def record_start(root: Path, ran_for: float, failed: bool) -> str | None:
    """After the companion of a freshly applied version ends: a failure at its very start counts; at two,
    app\\current goes back to the previous version, whose number is returned. A good run settles it."""
    path = state_path(root)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not failed or ran_for > EARLY:
        path.unlink(missing_ok=True)
        return None
    state["fails"] = state.get("fails", 0) + 1
    if state["fails"] < 2 or not state.get("previous") or not (root / "app" / state["previous"]).is_dir():
        path.write_text(json.dumps(state), encoding="utf-8")
        return None
    install.point_current(root, root / "app" / state["previous"])
    path.unlink(missing_ok=True)
    return state["previous"]


def checked_recently(root: Path, every: float, now: float | None = None) -> bool:
    stamp = root / "data" / "tmp" / "update-checked"
    now = time.time() if now is None else now
    try:
        if now - stamp.stat().st_mtime < every:
            return True
    except OSError:
        pass
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.touch()
    return False
