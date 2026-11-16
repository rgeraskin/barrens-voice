"""Putting a version of Barrens Voice in place - the installer's and the updater's one way
(docs/update-strategy.md).

A release archive holds companion/, addon/, pyproject.toml and uv.lock. A version is unpacked into
<install>\\app\\<version>, uv builds its environment there from uv.lock (exact: what the lock says and
nothing else; the libraries come from uv's cache in <install>\\cache\\uv as hard links, so a version
that keeps them costs no download and almost no disk), then <install>\\app\\current is pointed at it.
Run with any Python 3.11+: the installer runs this file through uv before any environment exists.

    python install.py --root <install> --archive barrens-voice-0.4.1.zip [--runtime cuda|directml]
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

INSTALL_MARK = "barrens-voice.install"        # bv.paths tells an install by it
PYTHON = "3.13"
KEEP = 2                                      # versions kept: the current one and one to go back to


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
    """app\\current -> this version (a junction on Windows: no administrator needed)."""
    current = root / "app" / "current"
    if current.is_junction():
        os.rmdir(current)                               # the link only, not the version behind it
    elif current.is_symlink():
        current.unlink()
    elif current.exists():
        shutil.rmtree(current)
    if sys.platform == "win32":
        # mklink /J: Windows' own way to make a junction, no administrator needed. (Junctions made in the
        # desktop session do not open over ssh on the test machine - check an install from the desktop.)
        subprocess.run(["cmd", "/c", "mklink", "/J", str(current), str(version_dir)], check=True,
                       capture_output=True)
    else:
        current.symlink_to(version_dir, target_is_directory=True)


def current_version(root: Path) -> str | None:
    current = root / "app" / "current"
    try:
        return Path(os.path.realpath(current)).name if current.exists() else None
    except OSError:
        return None


def version_key(version: str) -> tuple:
    import re
    return tuple(int(n) for n in re.findall(r"\d+", version)) or (0,)


def prune(root: Path, keep: int = KEEP) -> list[str]:
    """Old versions removed, the current one and the newest others kept; what is in use stays (Windows
    will not delete a loaded file) and goes next time."""
    current = current_version(root)
    versions = sorted((p for p in (root / "app").iterdir() if p.is_dir() and p.name not in ("current",)
                       and not p.name.endswith(".part")), key=lambda p: version_key(p.name), reverse=True)
    kept = [v for v in versions if v.name == current][:1]
    kept += [v for v in versions if v.name != current][: max(0, keep - len(kept))]
    removed = []
    for v in versions:
        if v not in kept:
            shutil.rmtree(v, ignore_errors=True)
            if not v.exists():
                removed.append(v.name)
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
