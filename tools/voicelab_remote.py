"""The voice lab (companion/bv/voicelab.py) on the Windows test machine, run from here: `mise run voicelab`.

- `mise run voicelab [-- --only troll-female/old] [-- --no-f5] [-- --steps 6,8]`: the working tree's companion/bv is
  copied to BV_LAB_DIR\\src and run there with the installed program's Python on its data (BV_DATA, BV_CACHE: its
  config.json, models and logs); the lab is BV_LAB_DIR\\lab. Refused while the game or the voice-over runs
  (Whisper and F5 take the video card; the game's files are read). `--steps` (the test line in fewer F5 steps too,
  bv/f5_schedule.py) needs the `onnx` package: installed once into BV_LAB_DIR\\pkgs, the lab's own, not the
  program's.
- `mise run voicelab -- --pick`: the lab's voices.yaml (edited there by ear) becomes companion/bv/voice_picks.yaml,
  what the players' banks are made of; check it with `git diff` before a commit.

The machine and its folders come from the environment, not the repository (.mise.local.toml, ignored by git):
BV_LAB_HOST (ssh's address), BV_LAB_INSTALL (the install's folder), BV_LAB_DIR (a working folder there).
"""
from __future__ import annotations

import base64
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "companion"))
from bv.voicelab import to_picks  # noqa: E402 - the lab file's own reading of voices
PICKS = ROOT / "companion" / "bv" / "voice_picks.yaml"
PICKS_HEAD = """# Голоса рас: из каких фраз игры собран образец голоса, выбрано на слух (python -m bv --voicelab, DEVELOPMENT.md,
# «Голоса рас: образцы на слух»). Голос из списка берёт ровно эти файлы игры, по порядку; пустой список — голоса нет.
# «- номер: "текст"» — текст фразы как есть, у всех игроков одинаковый; «- номер» — текст расслышит Whisper.
# Голоса, которых здесь нет, собираются сами (gamevoices.choose). Изменение файла пересобирает образцы у игроков.
"""


def powershell(host: str, script: str, check: bool = True, capture: bool = False):
    """`script` run by PowerShell on `host`, its output in UTF-8 (encoded: no quoting through ssh)."""
    script = ("[Console]::OutputEncoding = [Text.Encoding]::UTF8; $ErrorActionPreference = 'Stop'; "
              "$ProgressPreference = 'SilentlyContinue'\n" + script)
    encoded = base64.b64encode(script.encode("utf-16-le")).decode()
    return subprocess.run(["ssh", host, f"powershell -NoProfile -NonInteractive -EncodedCommand {encoded}"],
                          check=check, capture_output=capture, text=capture, encoding="utf-8" if capture else None)


# the lab's own packages (BV_LAB_DIR\\pkgs) for --steps: onnx rewrites the F5 model; without its dependencies, which
# the program has (numpy, protobuf, typing_extensions) - the program's own versions stay in use
LAB_PACKAGES = ["onnx==1.23.2", "ml_dtypes==0.6.0"]

# python labrun.py <the venv's site-packages> <bv's switches>: bv run by a Python outside the venv, with its packages
# (and the lab's own after them, BV_LAB_PKGS)
RUNNER = b"""import os, runpy, site, sys
site.addsitedir(sys.argv.pop(1))
if os.path.isdir(os.environ.get("BV_LAB_PKGS", "")):
    site.addsitedir(os.environ["BV_LAB_PKGS"])
try:   # ONNX Runtime's own warnings, in UTF-16 through ssh: noise in the task's output
    import onnxruntime
    onnxruntime.set_default_logger_severity(3)
except ImportError:
    pass
sys.argv[0] = "bv"
runpy.run_module("bv", run_name="__main__", alter_sys=True)
"""


def packed() -> bytes:
    """companion/bv as a .tgz, without caches, and labrun.py beside it."""
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w:gz") as tar:
        tar.add(ROOT / "companion" / "bv", arcname="bv",
                filter=lambda info: None if "__pycache__" in info.name else info)
        info = tarfile.TarInfo("labrun.py")
        info.size = len(RUNNER)
        tar.addfile(info, io.BytesIO(RUNNER))
    return data.getvalue()


def lab_to_picks(lab: str, picks: str, auto: dict, heard: dict | None = None) -> str:
    """voice_picks.yaml (`picks`) with the lab's choices by ear (bv.voicelab.to_picks): only the voices whose list
    differs from the automatic choice or whose text was corrected by hand; the voices the lab has not heard stay."""
    return to_picks(lab, picks, auto, PICKS_HEAD + "\n", heard)


def main(args: list[str]) -> int:
    env = {k: os.environ.get(k, "") for k in ("BV_LAB_HOST", "BV_LAB_INSTALL", "BV_LAB_DIR")}
    missing = [k for k, v in env.items() if not v]
    if missing:
        print(f"set {', '.join(missing)} (.mise.local.toml's [env]): the test machine's ssh address, the install's "
              "folder, a working folder there")
        return 2
    host, install, lab_dir = env["BV_LAB_HOST"], env["BV_LAB_INSTALL"].rstrip("\\"), env["BV_LAB_DIR"].rstrip("\\")
    if "--pick" in args:
        lab = f"'{lab_dir}\\lab"
        got = powershell(host, f"Get-Content -Raw -Encoding UTF8 {lab}\\voices.yaml'; '<<auto>>'; "
                               f"if (Test-Path {lab}\\auto.json') {{ Get-Content -Raw {lab}\\auto.json' }}; '<<heard>>'; "
                               f"if (Test-Path {lab}\\transcripts.json') {{ Get-Content -Raw -Encoding UTF8 {lab}\\transcripts.json' }}",
                         capture=True)
        lab, _, rest = got.stdout.partition("<<auto>>")
        auto, _, heard = rest.partition("<<heard>>")
        if not auto.strip():
            print("the lab has no auto.json (made by an older lab): run `mise run voicelab` once more first")
            return 1
        try:
            PICKS.write_text(lab_to_picks(lab, PICKS.read_text(encoding="utf-8"), json.loads(auto),
                                          json.loads(heard) if heard.strip() else {}), encoding="utf-8")
        except ValueError as e:
            print(e)
            return 1
        print(f"{PICKS.relative_to(ROOT)} written: only the voices chosen otherwise than automatically; check git diff")
        return 0
    busy = powershell(host, "$game = @(Get-Process Wow -ErrorAction SilentlyContinue).Count\n"
                            "$voice = @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match ' -m bv|labrun\\.py' }"
                            ").Count\n\"$game $voice\"", capture=True).stdout.split()
    if busy != ["0", "0"]:
        print("the game or the voice-over runs on the test machine: close them first")
        return 1
    with tempfile.TemporaryDirectory() as d:
        archive = Path(d) / "src.tgz"
        archive.write_bytes(packed())
        powershell(host, f"New-Item -ItemType Directory -Force '{lab_dir}\\src\\companion' | Out-Null")
        subprocess.run(["scp", "-q", str(archive), f"{host}:{lab_dir.replace(chr(92), '/')}/src.tgz"], check=True)
    passed = " ".join(f"'{a}'" for a in args)
    pkgs = f"{lab_dir}\\pkgs"
    marks = " -and ".join(f"(Test-Path '{pkgs}\\{p.replace('==', '-')}.dist-info')" for p in LAB_PACKAGES)
    get_onnx = "" if "--steps" not in args else f"""
if (-not ({marks})) {{
    & "$base\\python.exe" -m pip install --quiet --disable-pip-version-check --no-deps --only-binary ':all:' --upgrade --target '{pkgs}' {' '.join(LAB_PACKAGES)}
    if ($LASTEXITCODE) {{ exit $LASTEXITCODE }}
}}"""
    run = powershell(host, f"""
Remove-Item -Recurse -Force '{lab_dir}\\src\\companion\\bv' -ErrorAction SilentlyContinue
tar -xzf '{lab_dir}\\src.tgz' -C '{lab_dir}\\src\\companion'
$env:BV_DATA = '{install}\\data'; $env:BV_CACHE = '{install}\\cache'
Set-Location '{lab_dir}\\src\\companion'
# An ssh session does not go through the install's junctions (app\\current, uv's python\\cpython-3.13-...), and
# the venv's python.exe is uv's trampoline to the Python behind one: that Python itself, with the venv's packages.
$current = @((Get-Item '{install}\\app\\current').Target)[0]
$base = ((Get-Content "$current\\.venv\\pyvenv.cfg" | Select-String '^home').Line -split '=', 2)[1].Trim()
$link = Get-Item $base
if ($link.LinkType) {{ $base = @($link.Target)[0] }}{get_onnx}
$env:BV_LAB_PKGS = '{pkgs}'
& "$base\\python.exe" labrun.py "$current\\.venv\\Lib\\site-packages" --voicelab '{lab_dir}\\lab' {passed}
exit $LASTEXITCODE
""", check=False)
    return run.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
