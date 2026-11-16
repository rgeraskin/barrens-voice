"""Starting WoW through Battle.net, and telling whether it still runs (Windows only)."""
from __future__ import annotations

import ctypes
import os
import subprocess
from ctypes import wintypes
from pathlib import Path

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
    name = name.lower()
    return name.startswith("wow") and name.endswith(".exe") and "voice" not in name


def wow_running() -> bool:
    return any(is_wow(n) for n in process_names())


def process_paths(match) -> list[str]:
    """Full paths of the running programs whose file name `match` accepts (those this user may ask
    about: the game, run by the same user, is one of them)."""
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
                if handle:
                    buf = ctypes.create_unicode_buffer(1024)
                    size = wintypes.DWORD(len(buf))
                    if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                        paths.append(buf.value)
                    kernel32.CloseHandle(handle)
            ok = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return paths


def game_of_path(path: str) -> str | None:
    """Which game a Wow.exe belongs to, by its folder (…\\_forever_\\Wow.exe → "forever")."""
    from .dictionary import GAMES
    folder = Path(path).parent.name.lower()
    return next((game for game, name in GAMES.items() if name == folder), None)


def running_game() -> tuple[str, Path] | tuple[None, None]:
    """The game whose Wow.exe runs now and its folder (("forever", …\\_forever_)), or (None, None)."""
    for path in process_paths(is_wow):
        game = game_of_path(path)
        if game:
            return game, Path(path).parent
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


def launch(config: dict, log) -> bool:
    """Ask Battle.net to start the game of `game` (`launch_product` for Forever, WoWF;
    `launch_product_retail` for retail, WoW)."""
    exe = find_battlenet(config)
    if exe is None:
        log("Battle.net не найден: запустите игру сами (или укажите battlenet_exe в config.json)")
        return False
    from .dictionary import game_of
    product = (config.get("launch_product_retail", "WoW") if game_of(config) == "retail"
               else config.get("launch_product", "WoWF"))
    subprocess.Popen([str(exe), f"--exec=launch {product}"], close_fds=True,
                     creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    log(f"запускаю игру через Battle.net ({product}) ...")
    return True
