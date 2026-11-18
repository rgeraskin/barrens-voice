"""Updates of an installed Barrens Voice from GitHub Releases (docs/update-strategy.md).

A release carries barrens-voice-<version>.zip, manifest.json (the app's, addon's and protocol's
versions, the archive's name, size and SHA-256) and manifest.json.sig (ed25519, tools/sign.py). The
updater trusts a manifest only when it verifies with PUBLIC_KEY, and an archive only when it matches
the manifest; then bv.install puts the version beside the current one (uv builds its environment
from its uv.lock), its Python must import the launcher and the companion (`version_runs`), and app\\current
is pointed at it when the game is not running. If the new version's companion fails right at its start twice,
the launcher points app\\current back and remembers that version: it is not prepared by itself again, only
by «Обновить», until a newer one comes out (`record_start`, `refused`).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
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


def test_build(version: str) -> bool:
    """Whether a version is a test build ("0.4.1b1"): the stable channel never takes one."""
    key = install.version_key(version)
    return len(key) > 3 and key[-2] == 0


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


class WontStart(RuntimeError):
    """The version was built, but its Python cannot import the launcher or the companion."""

    def __init__(self, version: str, why: str):
        super().__init__(f"версия {install.display_version(version)} не запускается: {why}")
        self.version = version


# what version_runs imports in a version without bv/selfcheck.py: a fallback for a build made without it
# (no released client checks anything before 0.4.0, and every release from it ships bv/selfcheck.py)
FALLBACK_CHECK = ("import tkinter, bv.launcher.app, bv.__main__, bv.update; tkinter.Tcl(); "
                  "from cryptography.hazmat.primitives.asymmetric import ed25519")


def version_runs(version_dir: Path, python: Path | None = None) -> str | None:
    """Whether a built version can start at all: its Python imports the launcher, the companion and this
    updater, and Tk works. A release whose launcher fails at its start would never be rolled back (the rollback
    counts the companion's failures, and the launcher is what updates). None when it runs, else the error the
    check ended with. When the check itself could not run (no Python there, a timeout: an antivirus scan, a slow
    disk) RuntimeError - that says nothing of the version, the next check tries again.

    The version says itself what it needs: its bv/selfcheck.py, run as `python -m bv.selfcheck` in its
    companion folder, when it has one (the contract is in that module's docstring, and it binds every release:
    this launcher keeps running it); else FALLBACK_CHECK, the imports this launcher knew of."""
    import subprocess
    if python is None:
        python = version_dir / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    companion = version_dir / "companion"
    if (companion / "bv" / "selfcheck.py").is_file():
        command = [str(python), "-m", "bv.selfcheck"]
    else:
        command = [str(python), "-c", FALLBACK_CHECK]
    try:
        # its stderr in UTF-8, as it is read (a traceback in the locale's code page came out garbled)
        done = subprocess.run(command, cwd=companion, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=180, env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError) as e:
        raise RuntimeError(f"не получилось проверить, запускается ли версия: {e}") from e
    if done.returncode:
        lines = [line.strip() for line in (done.stderr or "").splitlines() if line.strip()]
        return lines[-1] if lines else f"код {done.returncode}"
    return None


def prepare(root: Path, archive: Path, log=print, manifest: dict | None = None) -> str:
    """The version unpacked beside the current one and its environment built (with the uv the release names,
    which then replaces the installed one), then checked to start (WontStart if not); not made current yet."""
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
    why = version_runs(folder)
    if why:
        raise WontStart(version, why)
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


def write_json(path: Path, data: dict) -> None:
    """Through a temporary file: a launcher killed meanwhile leaves the old file or the new one, never half."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, path)


def refused_path(root: Path) -> Path:
    return root / "data" / "update-refused.json"


def refused(root: Path) -> str | None:
    """The version that failed here (went back from, or would not start): not prepared by itself again."""
    try:
        version = json.loads(refused_path(root).read_text(encoding="utf-8")).get("version")
    except (OSError, ValueError, AttributeError):
        return None
    return version if isinstance(version, str) and version else None


def refuse(root: Path, version: str | None) -> None:
    """Remember the version that failed here (None: forget it)."""
    path = refused_path(root)
    try:
        if version is None:
            path.unlink(missing_ok=True)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"version": version}), encoding="utf-8")
    except OSError:
        pass


def apply(root: Path, version: str) -> None:
    """app\\current -> `version`, remembering the one before, to go back to if this one fails to start. The
    watch (update.json) is written before the switch: a switch without it could never go back (and an error
    after the switch made a retry record the version as its own previous one); a failed switch removes it."""
    previous = install.current_version(root)
    path = state_path(root)
    if previous != version:                         # already current (a retry after the switch): watched as it is
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json(path, {"version": version, "previous": previous, "fails": 0})
        try:
            install.point_current(root, root / "app" / version)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
    note_version(root, version)


def record_start(root: Path, ran_for: float, failed: bool | None) -> str | None:
    """After the companion of a freshly applied version ends: a failure at its very start (`failed` True)
    counts; at two, app\\current goes back to the previous version, whose number is returned. A good run
    (False, or any end after EARLY) settles it: update.json goes, the versions before the previous one are
    pruned. None is no verdict - the companion stopped for a reason that is not the version's (started again
    online, another companion, config.json, an error it explained): nothing changes, the next start decides."""
    path = state_path(root)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    current = install.current_version(root)
    if current is not None and current != state.get("version"):
        path.unlink(missing_ok=True)                # the switch it was written for did not happen
        return None
    if failed is None and ran_for <= EARLY:
        return None
    if not failed or ran_for > EARLY:
        path.unlink(missing_ok=True)
        try:                                        # settled: the versions before the one to go back to go
            install.prune(root)
        except OSError:
            pass
        return None
    state["fails"] = state.get("fails", 0) + 1
    if state["fails"] < 2 or not state.get("previous") or not (root / "app" / state["previous"]).is_dir():
        path.write_text(json.dumps(state), encoding="utf-8")
        return None
    install.point_current(root, root / "app" / state["previous"])
    note_version(root, state["previous"])
    refuse(root, state.get("version"))
    path.unlink(missing_ok=True)
    return state["previous"]


BUSY = ("downloading", "preparing", "ready")


class Updater:
    """The launcher's update flow without its window (bv/launcher/app.py draws its state and calls it):
    `check` finds a newer release of the channel and, with automatic updates on, `prepare`s it; `due`
    says when the prepared version may become current (no game, no voice-over, nothing else on the way);
    `apply` makes it so. `status`: "" | "downloading" | "preparing" | "ready" | "error" (an error is tried
    again at the next check - but a version that was built and does not start (WontStart) is refused: only
    «Обновить» or a newer version tries again)."""

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
        channel = settings.get("update_channel", "stable")
        try:
            found = latest(channel, self.fetch, self.public)
        except Exception as e:  # noqa: BLE001 - offline, GitHub down: the next check
            if getattr(e, "code", None) != 404:          # 404: no release in this channel yet
                self.detail(f"проверка обновлений: {e}")
            return None
        if found is None:
            self.say("описание выпуска без верной подписи — не обновляюсь", "WARN")
            return None
        if channel != "beta" and test_build(found["version"]):
            return None                                 # releases/latest serving a test build: not for this channel
        if not newer(found["version"], self.current) or self.status in BUSY:
            return None
        name = install.display_version(found["version"])
        refused_version = refused(self.root)
        if refused_version and newer(found["version"], refused_version):
            refuse(self.root, None)                     # a newer one than the version that failed: as usual
        # only that very version (an older one - another channel's - is not the one that failed here)
        bad = refused_version == found["version"]
        told = self.found is not None and self.found["version"] == found["version"]
        if not told:
            self.say(f"вышла версия {name}")
        self.found = found
        if bad:
            if not told:
                self.say(f"версия {name} не запустилась у вас — сама не ставлю, «Обновить» попробует снова", "WARN")
        elif settings.get("auto_update", True):
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
        downloads = self.root / "cache" / "downloads"
        try:
            self.status = "downloading"
            self.say(f"скачиваю версию {name} ...")
            archive = download(found, downloads, fetch_stream=self.fetch_stream)
            self.status = "preparing"
            self.say(f"готовлю версию {name} ...")
            self.ready = prepare(self.root, archive, log=self.detail, manifest=found)
            self.status = "ready"
            self.say(f"версия {name} готова — установится, когда закроете игру")
            return self.ready
        except Exception as e:  # noqa: BLE001 - the current version goes on
            if isinstance(e, WontStart):
                refuse(self.root, e.version)        # tried again by «Обновить» or with a newer version only
            self.status = "error"
            self.say(f"обновление не удалось: {e}", "WARN")
            return None
        finally:
            for leftover in downloads.glob("barrens-voice-*"):   # unpacked or refused: the archive is not needed
                try:
                    leftover.unlink()
                except OSError:
                    pass

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


def relaunch_command(starter: str, resident: bool, updated: bool = False) -> str:
    """How the launcher starts anew a moment after it ends (cmd waits ~2 s: the old one frees its mutex).
    `updated`: into a version just applied, which knows --updated (not a version gone back to: an older
    launcher stops at a switch it does not know) - that start does not start the game."""
    return (f'cmd /c ping -n 3 127.0.0.1 >nul & start "" {starter}' + (" --tray" if resident else "")
            + (" --updated" if updated else ""))
