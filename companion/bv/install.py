"""Putting a version of Barrens Voice in place - the installer's and the updater's one way
(docs/update-strategy.md).

A release archive holds companion/, addon/, pyproject.toml and uv.lock. A version is unpacked into
<install>\\app\\<version>, uv builds its environment there from uv.lock (exact: what the lock says and
nothing else; the libraries come from uv's cache in <install>\\cache\\uv as hard links, so a version
that keeps them costs no download and almost no disk), then <install>\\app\\current is pointed at it.
Run with any Python 3.12+ (os.path.isjunction): the installer runs this file with uv's Python 3.13 before any
environment exists.

    python install.py --root <install> --archive barrens-voice-0.4.1.zip [--runtime cuda|directml]
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

INSTALL_MARK = "barrens-voice.install"        # bv.paths tells an install by it
PYTHON = "3.13"
KEEP = 2                                      # versions kept: the current one and one to go back to
LAUNCHER = Path("companion") / "BarrensVoice.pyw"   # what the starter runs (installer/launcher.cs)


def uv_env(root: Path, version_dir: Path) -> dict:
    """uv's settings for an install: its own Python, cache and the version's environment."""
    return {**os.environ,
            "UV_PROJECT_ENVIRONMENT": str(version_dir / ".venv"),
            "UV_CACHE_DIR": str(root / "cache" / "uv"),
            "UV_PYTHON_INSTALL_DIR": str(root / "python"),
            "UV_PYTHON_PREFERENCE": "only-managed",
            "UV_LINK_MODE": "hardlink",
            "UV_NO_CONFIG": "1"}


def runtime_of(root: Path) -> str:
    """The ONNX Runtime build this install was made with (its mark file), for its updates."""
    import json
    try:
        return json.loads((root / INSTALL_MARK).read_text(encoding="utf-8")).get("runtime") or runtime_for_this_pc()
    except (OSError, ValueError):
        return runtime_for_this_pc()


def runtime_for_this_pc() -> str:
    """ONNX Runtime's build for the video card: "cuda" with an NVIDIA driver, else "directml"."""
    return "cuda" if shutil.which("nvidia-smi") else "directml"


def unpack(archive: Path, root: Path) -> tuple[str, Path]:
    """The release into app\\<version> (beside, then renamed: a broken download leaves no half version).
    Returns (version, its folder)."""
    with zipfile.ZipFile(archive) as z:
        version = read_version(z.read("pyproject.toml").decode("utf-8"))
        target = root / "app" / version
        if (target / "uv.lock").is_file():
            return version, target                      # already unpacked (a retry): keep its .venv
        part = target.with_name(version + ".part")
        shutil.rmtree(part, ignore_errors=True)
        z.extractall(part)
    shutil.rmtree(target, ignore_errors=True)
    part.rename(target)
    return version, target


def read_version(pyproject: str) -> str:
    import tomllib
    return tomllib.loads(pyproject)["project"]["version"]


def build(root: Path, version_dir: Path, runtime: str, uv: Path, log=print) -> None:
    """The version's environment, exactly as its uv.lock says."""
    command = [str(uv), "sync", "--frozen", "--no-dev", "--extra", runtime, "--python", PYTHON,
               "--project", str(version_dir)]
    log("окружение: " + " ".join(command[1:]))
    # no console window of its own (the launcher is pythonw); its lines go to the log instead
    proc = subprocess.Popen(command, env=uv_env(root, version_dir), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace",
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    for line in proc.stdout:
        if line.strip():
            log("    " + line.rstrip())
    if proc.wait():
        raise RuntimeError(f"uv sync завершился с кодом {proc.returncode}")


def point_current(root: Path, version_dir: Path) -> None:
    """app\\current -> this version (a junction on Windows: no administrator needed). The new link is made
    beside as current.new and swapped in by two renames: a failure on the way leaves the old current in place
    (before, current was removed first and a failed mklink left none - «установлен не до конца»). A folder
    without the launcher's script is refused (FileNotFoundError): pointed at, it left nothing the starter could run."""
    if not whole(version_dir):
        raise FileNotFoundError(f"нет {version_dir / LAUNCHER}")
    app = root / "app"
    current, fresh, old = app / "current", app / "current.new", app / "current.old"
    for leftover in (fresh, old):                       # a swap cut short last time
        remove_link(leftover)
    make_link(fresh, version_dir)
    if os.path.lexists(current):
        try:
            os.rename(current, old)
        except OSError:
            remove_link(fresh)
            raise
    try:
        os.rename(fresh, current)
    except OSError:
        if os.path.lexists(old) and not os.path.lexists(current):
            os.rename(old, current)                     # back as it was
        remove_link(fresh)
        raise
    # switched: what follows cannot undo it. The old link goes now or as a leftover at the next switch; a crash
    # between the two renames leaves current.new and current.old, which the starter (installer/launcher.cs) uses
    try:
        remove_link(old)
    except OSError:
        pass
    place_starter(root, version_dir)


def repair_current(root: Path, running: Path) -> bool:
    """app\\current made again after a switch cut short between its two renames (point_current), which left only
    current.new and current.old: the starter runs one of them, but nothing made current again until the next
    update, which then had no version to go back to. Pointed at `running` - the version this launcher is, the
    one the starter chose - when one of the two links points at it. current.new is the version switched to: the
    new one of an update, still watched by update.json, or the previous one of a rollback, whose refusal of the
    failed version is written before it (bv/update.py record_start). current.old is the one switched from. When
    the running version is not the one update.json watches, that watch is dropped at the companion's next end
    (a switch that did not happen, or a rollback already done). Whether it was made."""
    app = root / "app"
    if os.path.exists(app / "current"):
        return False
    target = Path(os.path.realpath(running))
    if not any(os.path.lexists(link) and Path(os.path.realpath(link)) == target
               for link in (app / "current.new", app / "current.old")):
        return False
    try:
        point_current(root, target)
    except OSError:
        return False
    return True


def whole(version_dir: Path) -> bool:
    """Whether a version's folder holds the launcher's script: one to point app\\current at."""
    return (version_dir / LAUNCHER).is_file()


def make_link(link: Path, target: Path) -> None:
    """`link` -> the folder `target`: a junction on Windows, a symlink elsewhere (the tests)."""
    if sys.platform != "win32":
        link.symlink_to(target, target_is_directory=True)
        return
    try:
        # CPython's private helper (in _winapi since 3.5, for its own tests; there in 3.13): no shell, so no
        # quoting of the path. It may report the error of its privilege step after making the link: checked below.
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
    except (ImportError, AttributeError, OSError):
        if not os.path.isjunction(link):
            if os.path.isdir(link):
                os.rmdir(link)                          # its empty folder, the link not set
            # mklink /J: Windows' own way. One string, both paths quoted: cmd would split a folder named
            # with "&" (list2cmdline quotes only for spaces). (Junctions made in the desktop session do not
            # open over ssh on the test machine - check an install from the desktop.)
            subprocess.run(f'cmd /c mklink /J "{link}" "{target}"', check=True, capture_output=True)
    if not os.path.isjunction(link) or Path(os.path.realpath(link)) != Path(os.path.realpath(target)):
        raise OSError(f"не получилось связать {link} с {target}")


def remove_link(path: Path) -> None:
    """A link (junction or symlink) removed, not what it points at; a real folder in its place removed whole."""
    if os.path.isjunction(path):
        os.rmdir(path)
    elif os.path.islink(path):
        os.unlink(path)
    elif os.path.isdir(path):
        shutil.rmtree(path)
    elif os.path.lexists(path):
        os.unlink(path)


STARTER = "Barrens Voice.exe"


def place_starter(root: Path, version_dir: Path) -> bool:
    """The version's Barrens Voice.exe (in its release archive) to the install's root, where a player finds
    it and the shortcuts point: put there when missing or changed, so updates keep it too. False when it
    could not be (an old release without it, or the file in use: the one there goes on working)."""
    source, target = version_dir / STARTER, root / STARTER
    if not source.is_file():
        return False
    try:
        if target.is_file() and target.read_bytes() == source.read_bytes():
            return True
        shutil.copyfile(source, target)
        return True
    except OSError:
        return False


def current_version(root: Path) -> str | None:
    current = root / "app" / "current"
    try:
        return Path(os.path.realpath(current)).name if current.exists() else None
    except OSError:
        return None


def version_key(version: str) -> tuple:
    """Versions in order, a test build before its release: "0.4.0b5" (or "v0.4.0-beta.5") < "0.4.0" <
    "0.4.1". Anything without numbers sorts first."""
    import re
    m = re.match(r"v?(\d+(?:\.\d+)*)(?:-?(?:b|beta)\.?(\d+))?", (version or "").strip())
    if not m:
        return (0,)
    numbers = tuple(int(n) for n in m.group(1).split("."))
    numbers += (0,) * (3 - len(numbers))
    return numbers + ((0, int(m.group(2))) if m.group(2) else (1, 0))


def display_version(version: str) -> str:
    """For people: "0.4.0b5" -> "0.4.0 beta 5"."""
    import re
    return re.sub(r"b(\d+)$", r" beta \1", version or "?")


def release_tag(version: str) -> str:
    """The git tag of a version: "0.4.0b5" -> "v0.4.0-beta.5", "0.4.0" -> "v0.4.0"."""
    import re
    return "v" + re.sub(r"b(\d+)$", r"-beta.\1", version)


# a version's folder in app\\ is named by its pyproject.toml version: "0.4.1", "0.4.0b5"
VERSION_NAME = re.compile(r"\d+(?:\.\d+)*(?:b\d+)?")


def prune(root: Path, keep: int = KEEP, also=(), watched=None, refused=()) -> list[str]:
    """Versions older than the current one removed but the newest keep-1 of them (to go back to; not one `refused`
    here - a version that failed is none to go back to, the one that worked before it is) and those named
    in `also` or by `watched()` - update.json's version and previous, asked only after the current version is
    read: a switch writes its watch before it moves app\\current (bv/update.py apply), so a switch this prune
    sees done is always seen with its watch (read before, an update applied meanwhile lost its previous). A version newer than the current one is never removed: it may be prepared
    and waiting for its switch, or refused here (it goes once a newer one is current) - by number alone a refused
    test build left on disk kept itself and pruned the prepared version, and the switch pointed at nothing.
    Nor what current.new or current.old points at (a switch cut short), nor anything while there is no current
    version, nor a folder whose name is not a version's (VERSION_NAME: «backup», «0.4.1 - копия» are the
    player's). A version is renamed to <version>.pruned before it is removed: a prune cut short (the launcher
    ended) leaves no half version under a version's name, and the rest goes at the next prune. What is in use
    stays (Windows will not delete a loaded file, nor rename a folder with one) and goes next time."""
    app = root / "app"
    for leftover in app.glob("*.pruned"):
        if leftover.is_dir() and VERSION_NAME.fullmatch(leftover.name.removesuffix(".pruned")):
            shutil.rmtree(leftover, ignore_errors=True)
    current = current_version(root)
    if current is None:
        return []
    keep_names = {current, *(v for v in (*also, *(watched() if watched else ())) if isinstance(v, str) and v)}
    for link in (app / "current.new", app / "current.old"):
        if os.path.lexists(link):
            keep_names.add(Path(os.path.realpath(link)).name)
    older = sorted((p for p in app.iterdir() if VERSION_NAME.fullmatch(p.name) and p.is_dir()
                    and not p.is_symlink() and not p.is_junction() and version_key(p.name) < version_key(current)),
                   key=lambda p: version_key(p.name), reverse=True)
    keep_names.update(v.name for v in [v for v in older if v.name not in refused][: max(0, keep - 1)])
    removed = []
    for v in older:
        if v.name in keep_names:
            continue
        gone = v.with_name(v.name + ".pruned")
        try:
            os.rename(v, gone)
        except OSError:
            continue                                    # in use (or a leftover of the same name): next time
        removed.append(v.name)
        shutil.rmtree(gone, ignore_errors=True)
    return removed


def install(root: Path, archive: Path, runtime: str | None, uv: Path, log=print) -> str:
    """Unpack, build and make current; returns the version."""
    import json
    root.mkdir(parents=True, exist_ok=True)
    runtime = runtime or runtime_for_this_pc()
    (root / INSTALL_MARK).write_text(json.dumps({"app": "Barrens Voice", "runtime": runtime}) + "\n", encoding="utf-8")
    for sub in ("app", "data", "cache"):
        (root / sub).mkdir(exist_ok=True)
    version, folder = unpack(archive, root)
    build(root, folder, runtime, uv, log)
    point_current(root, folder)
    log(f"Barrens Voice {version} установлен в {root}")
    return version


def main() -> int:
    parser = argparse.ArgumentParser(description="Put a Barrens Voice release in place")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--runtime", choices=("cuda", "directml"))
    parser.add_argument("--uv", type=Path, default=None, help="uv.exe (default: next to the install)")
    args = parser.parse_args()
    uv = args.uv or args.root / "uv.exe"
    install(args.root, args.archive, args.runtime, uv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
