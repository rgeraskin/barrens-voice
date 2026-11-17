"""Starting WoW through Battle.net, and telling whether it still runs (Windows only)."""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path, PureWindowsPath

TH32CS_SNAPPROCESS = 0x2


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]


def process_names() -> set[str]:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    names = set()
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(entry)
    try:
        ok = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            names.add(entry.szExeFile.lower())
            ok = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return names


def is_wow(name: str) -> bool:
    """A program file named like the game's (Wow.exe, WowClassic.exe) - so are WowUp.exe and other
    tools: only a first sieve before the path (`is_game`)."""
    name = name.lower()
    return name.startswith("wow") and name.endswith(".exe") and "voice" not in name


def is_game(path: str) -> bool:
    """Whether a running program (its full path) is the game: a Wow*.exe in one of the games' folders
    (…\\_forever_\\Wow.exe). The companion's exit with the game, its launch and its window all ask this."""
    return is_wow(PureWindowsPath(path).name) and game_of_path(path) is not None


def wow_running() -> bool:
    """The game runs: a Wow.exe in a game's folder (`is_game`). The exit with the game asks this - a tool
    named like the game (WowUp.exe) must not keep the companion running after the game closed, so a
    program whose path cannot be read is not the game here."""
    return any(is_game(p) for p in process_paths(is_wow))


def wow_may_run() -> bool:
    """The game may run: `wow_running`, or a program named like the game (`is_wow`) whose path cannot be
    read (run as another user or as administrator, say). The launch asks this: a second game started by
    Battle.net is worse than a launch left to the player, who sees «игра уже запущена» in the log."""
    unread: list[str] = []
    return any(is_game(p) for p in process_paths(is_wow, unread)) or bool(unread)


def process_paths(match, unread: list[str] | None = None) -> list[str]:
    """Full paths of the running programs whose file name `match` accepts (those this user may ask
    about: the game, run by the same user, is one of them). The names of those whose path cannot be
    read go to `unread`."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.OpenProcess.restype = wintypes.HANDLE
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(entry)
    paths = []
    try:
        ok = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            if match(entry.szExeFile):
                handle = kernel32.OpenProcess(0x1000, False, entry.th32ProcessID)   # QUERY_LIMITED_INFORMATION
                path = None
                if handle:
                    buf = ctypes.create_unicode_buffer(1024)
                    size = wintypes.DWORD(len(buf))
                    if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                        path = buf.value
                    kernel32.CloseHandle(handle)
                if path:
                    paths.append(path)
                elif unread is not None:
                    unread.append(entry.szExeFile)
            ok = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return paths


def game_of_path(path: str) -> str | None:
    """Which game a Wow.exe belongs to, by its folder (…\\_forever_\\Wow.exe → "forever")."""
    from .dictionary import GAMES
    folder = PureWindowsPath(path).parent.name.lower()
    return next((game for game, name in GAMES.items() if name == folder), None)


def running_game() -> tuple[str, Path] | tuple[None, None]:
    """The game whose Wow.exe runs now and its folder (("forever", …\\_forever_)), or (None, None)."""
    for path in process_paths(is_wow):
        if is_game(path):
            return game_of_path(path), Path(path).parent
    return None, None


def find_battlenet(config: dict) -> Path | None:
    if config.get("battlenet_exe"):
        path = Path(config["battlenet_exe"])
        return path if path.exists() else None
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                             r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Battle.net")
        location, _ = winreg.QueryValueEx(key, "InstallLocation")
        path = Path(location) / "Battle.net.exe"
        if path.exists():
            return path
    except OSError:
        pass
    for base in (os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), r"C:\Program Files", "D:\\", "E:\\"):
        path = Path(base) / "Battle.net" / "Battle.net.exe"
        if path.exists():
            return path
    return None


def launch(config: dict, log, game_running=None) -> bool:
    """Ask Battle.net to start the game of `game` (`launch_product` for Forever, WoWF;
    `launch_product_retail` for retail, WoW) - unless a game runs already: the player may have started it
    while the voice bank was being built before this launch, and a second command starts a second game
    (`wow_may_run`: a program named like the game whose path cannot be read counts)."""
    running = game_running or (wow_may_run if sys.platform == "win32" else (lambda: False))
    if running():
        log("игра уже запущена — второй раз не запускаю")
        return False
    exe = find_battlenet(config)
    if exe is None:
        log("Battle.net не найден: укажите его в «Настройках»")
        return False
    from .dictionary import game_of
    product = (config.get("launch_product_retail", "WoW") if game_of(config) == "retail"
               else config.get("launch_product", "WoWF"))
    command = [str(exe), f"--exec=launch {product}"]
    cold = not battlenet_running()

    def send() -> None:
        subprocess.Popen(command, close_fds=True, creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    send()
    log("запускаю игру через Battle.net ...")
    log(f"    Battle.net: --exec=launch {product}")
    if cold:          # Battle.net was not running: this first command only starts it (see follow_cold_start)
        threading.Thread(target=follow_cold_start, args=(send, log), daemon=True, name="battlenet-cold").start()
    return True


def battlenet_running() -> bool:
    """Is Battle.net running? True when it cannot be told (off Windows): then nothing is sent again."""
    try:
        return "battle.net.exe" in process_names()
    except (AttributeError, OSError):
        return True


def battlenet_window() -> bool:
    """Is Battle.net's main window up (visible, titled «Battle.net»): logged in, it takes commands."""
    try:
        import win32gui
        import win32process
    except ImportError:
        return False
    found = []

    def check(hwnd, _):
        if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd) == "Battle.net":
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            found.append(pid)
    try:
        win32gui.EnumWindows(check, None)
    except Exception:  # noqa: BLE001 - only a hint
        return False
    return bool(found)


def follow_cold_start(send, log, game_running=None, ready=None, sleep=time.sleep, clock=time.monotonic,
                      limit: float = 120.0) -> bool:
    """Battle.net started by `--exec=launch` itself drops that command while it loads and logs in:
    the window opens and the game does not start. So: wait for the game; once Battle.net's window is up
    (or after a minute: it may start minimized to the tray) with no game, send the command once more -
    only once: a command sent to a Battle.net that took the first one may start a second game. True
    when the game came (`wow_may_run`, as for the launch: never a second command to a second game)."""
    game_running = game_running or wow_may_run
    ready = ready or battlenet_window
    start, resent = clock(), False
    while clock() - start < limit:
        if game_running():
            return True
        if not resent and (ready() or clock() - start > 60):
            sleep(5)                       # the window is drawn a moment before it takes commands
            if game_running():
                return True
            send()
            resent = True
            log("Battle.net только что запустился и пропустил команду — прошу запустить игру ещё раз")
        sleep(1)
    if not game_running():
        log("Battle.net не запустил игру — нажмите «Играть» в нём")
    return game_running()
