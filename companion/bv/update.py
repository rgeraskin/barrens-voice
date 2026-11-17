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
RELEASES = f"https://api.github.com/repos/{REPO}/releases?per_page=100"
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


def signed_manifest(base: str, fetch=get, public: str = PUBLIC_KEY) -> dict | None:
    """The manifest at `base` if its signature holds, with "base": where its archive is."""
    raw = fetch(base + "manifest.json")
    if not verify(raw, fetch(base + "manifest.json.sig").decode("ascii", "replace"), public):
        return None
    return {**json.loads(raw), "base": base}


def latest(channel: str = "stable", fetch=get, public: str = PUBLIC_KEY) -> dict | None:
    """The newest signed release of the channel: "stable" (the latest release) or "beta" (pre-releases too:
    of the releases that carry a manifest, drafts skipped, the one with the highest version by its tag - GitHub
    lists them by the tag as text, so v0.4.0-beta.10 came after beta.2 and beta 9 was taken for the newest)."""
    if channel != "beta":
        return signed_manifest(STABLE, fetch, public)
    tags = [r["tag_name"] for r in json.loads(fetch(RELEASES)) if not r.get("draft")
            and {"manifest.json", "manifest.json.sig"} <= {a.get("name") for a in r.get("assets", [])}]
    if not tags:
        return None
    newest = max(tags, key=install.version_key)
    return signed_manifest(f"https://github.com/{REPO}/releases/download/{newest}/", fetch, public)


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


def release_uv(root: Path, manifest: dict, log=print, fetch=None) -> Path:
    """The uv the release names (manifest "uv"): the installed uv.exe when it is that version, else that
    one downloaded, checked against the signed manifest's SHA-256 and unpacked beside as uv.new.exe."""
    import io
    import zipfile
    want, current = manifest.get("uv"), root / "uv.exe"
    if not want or uv_version(current) == want.get("version"):
        return current
    log(f"uv {want['version']} ...")
    data = (fetch or get)(want["url"])
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
    try:
        install.build(root, folder, install.runtime_of(root), uv, log)
    except BaseException:
        if uv.name == "uv.new.exe":                # the new uv failed: the installed one stays, nothing left over
            uv.unlink(missing_ok=True)
        raise
    if uv.name == "uv.new.exe":
        os.replace(uv, root / "uv.exe")
    return version


# the installer's entry in Windows «Apps» (Inno Setup: the AppId of installer/BarrensVoice.iss, "_is1")
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{6F2E1C55-3B8D-4E57-9C61-0B6E2A7D4F19}_is1"


def note_version(root: Path, version: str, reg=None) -> bool:
    """Windows «Apps» shows the version the installer put; after an update (or a rollback) it is the version
    in use. Only when the entry is this install's (its InstallLocation) and the version is known; whether it was
    changed."""
    if not version:
        return False
    if reg is None:
        if os.name != "nt":
            return False
        import winreg as reg
    try:
        with reg.OpenKey(reg.HKEY_CURRENT_USER, UNINSTALL_KEY, 0, reg.KEY_READ | reg.KEY_SET_VALUE) as key:
            location = reg.QueryValueEx(key, "InstallLocation")[0]
            if Path(location.rstrip("\\/")).resolve() != Path(root).resolve():
                return False
            reg.SetValueEx(key, "DisplayVersion", 0, reg.REG_SZ, version)
            return True
    except OSError:
        return False


def state_path(root: Path) -> Path:
    return root / "data" / "tmp" / "update.json"


def apply(root: Path, version: str) -> None:
    """app\\current -> `version`, remembering the one before, to go back to if this one fails to start."""
    previous = install.current_version(root)
    install.point_current(root, root / "app" / version)
    note_version(root, version)
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
    note_version(root, state["previous"])
    path.unlink(missing_ok=True)
    return state["previous"]


BUSY = ("downloading", "preparing", "ready")


class Updater:
    """The launcher's update flow without its window (bv/launcher/app.py draws its state and calls it):
    `check` finds a newer release of the channel and, with automatic updates on, `prepare`s it; `due`
    says when the prepared version may become current (no game, no voice-over, nothing else on the way);
    `apply` makes it so. `status`: "" | "downloading" | "preparing" | "ready" | "error" (an error is tried
    again at the next check)."""

    def __init__(self, root: Path, current: str, settings, say, detail=None, fetch=get, fetch_stream=None,
                 public: str = PUBLIC_KEY):
        self.root, self.current, self.settings, self.say = Path(root), current, settings, say
        self.detail = detail or (lambda m: None)
        self.fetch, self.fetch_stream, self.public = fetch, fetch_stream, public
        self.found: dict | None = None
        self.status = ""
        self.ready: str | None = None
        self.apply_failed: str | None = None    # the prepared version whose switch failed: not tried by itself again

    def check(self) -> dict | None:
        """The newer release found now (None when there is none, or it is being made ready already)."""
        settings = self.settings()
        try:
            found = latest(settings.get("update_channel", "stable"), self.fetch, self.public)
        except Exception as e:  # noqa: BLE001 - offline, GitHub down: the next check
            if getattr(e, "code", None) != 404:          # 404: no release in this channel yet
                self.detail(f"проверка обновлений: {e}")
            return None
        if found is None:
            self.say("описание выпуска без верной подписи — не обновляюсь", "WARN")
            return None
        if not newer(found["version"], self.current) or self.status in BUSY:
            return None
        if self.found is None or self.found["version"] != found["version"]:
            self.say(f"вышла версия {install.display_version(found['version'])}")
        self.found = found
        if settings.get("auto_update", True):
            self.prepare()
        return found

    def url(self) -> str | None:
        """The page of the release found."""
        if not self.found:
            return None
        return f"https://github.com/{REPO}/releases/tag/{install.release_tag(self.found['version'])}"

    def prepare(self) -> str | None:
        """Download, check and build the release found beside the current version; its version when ready."""
        found = self.found
        if not found or self.status in BUSY:
            return None
        name = install.display_version(found["version"])
        try:
            self.status = "downloading"
            self.say(f"скачиваю версию {name} ...")
            archive = download(found, self.root / "cache" / "downloads", fetch_stream=self.fetch_stream)
            self.status = "preparing"
            self.say(f"готовлю версию {name} ...")
            self.ready = prepare(self.root, archive, log=self.detail, manifest=found)
            self.status = "ready"
            self.say(f"версия {name} готова — установится, когда закроете игру")
            return self.ready
        except Exception as e:  # noqa: BLE001 - the current version goes on
            self.status = "error"
            self.say(f"обновление не удалось: {e}", "WARN")
            return None

    def due(self, game_running: bool, companion_running: bool, busy: bool) -> bool:
        """Whether the prepared version may become current now: never under a running game or voice-over, and
        not again by itself after its switch failed (the next start of the launcher tries it anew)."""
        return (bool(self.ready) and self.ready != self.apply_failed and not game_running and not companion_running
                and not busy)

    def apply(self) -> str | None:
        """app\\current -> the prepared version (the launcher restarts into it: relaunch_command); None when the
        switch failed - the current version stays and the prepared one stays ready."""
        version = self.ready
        if not version:
            return None
        try:
            apply(self.root, version)
        except Exception as e:  # noqa: BLE001 - the current version goes on
            self.apply_failed = version
            self.say(f"не получилось перейти на версию {install.display_version(version)}: {e}", "WARN")
            return None
        self.ready, self.status = None, ""
        self.say(f"перехожу на версию {install.display_version(version)}")
        return version


def relaunch_command(starter: str, resident: bool) -> str:
    """How the launcher starts anew a moment after it ends (cmd waits ~2 s: the old one frees its mutex)."""
    return f'cmd /c ping -n 3 127.0.0.1 >nul & start "" {starter}' + (" --tray" if resident else "")
