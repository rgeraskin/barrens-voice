"""Finding the WoW window and its client area in physical screen pixels (Windows only)."""
from __future__ import annotations

import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def make_dpi_aware() -> None:
    """Physical pixels everywhere (window rects and screen grabs agree)."""
    try:
        ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)
    except (OSError, AttributeError):
        try:
            user32.SetProcessDPIAware()
        except (OSError, AttributeError):
            pass


def _path_of(hwnd: int) -> str:
    """The full path of the program the window belongs to; "" when Windows does not say."""
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value
        return ""
    finally:
        kernel32.CloseHandle(handle)


def frame_offset(hwnd: int) -> tuple[int, int]:
    """Where the client area starts inside what Windows Graphics Capture shows of the window (its
    extended frame bounds): the title bar and border in windowed mode, (0, 0) in fullscreen."""
    try:
        bounds = wintypes.RECT()
        ctypes.WinDLL("dwmapi").DwmGetWindowAttribute(hwnd, 9, ctypes.byref(bounds), ctypes.sizeof(bounds))
        origin = wintypes.POINT(0, 0)
        user32.ClientToScreen(hwnd, ctypes.byref(origin))
        return origin.x - bounds.left, origin.y - bounds.top
    except OSError:
        return 0, 0


def find_wow_window() -> tuple[int, tuple[int, int, int, int]] | None:
    """(hwnd, (left, top, width, height) of its client area) of the largest visible, not minimised
    window of the game (`launch.is_game`: not WowUp.exe and the like), in physical screen pixels; None
    when there is none."""
    from .launch import is_game
    best: list = []

    def visit(hwnd, _):
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        if not is_game(_path_of(hwnd)):
            return True
        rect = wintypes.RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
            return True
        origin = wintypes.POINT(0, 0)
        user32.ClientToScreen(hwnd, ctypes.byref(origin))
        width, height = rect.right - rect.left, rect.bottom - rect.top
        if width > 200 and height > 200:
            best.append((width * height, hwnd, (origin.x, origin.y, width, height)))
        return True

    user32.EnumWindows(EnumWindowsProc(visit), 0)
    if not best:
        return None
    _, hwnd, rect = max(best)
    return hwnd, rect
