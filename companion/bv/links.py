"""Pages the addon asks the companion to open in the browser or put on the clipboard (a click in its
settings: an addon can do neither - LaunchURL and CopyToClipboard are Blizzard's own). The addon
sends only a name; only the addresses here are ever used, the same as the addon's ns.LINKS (Core.lua)."""
from __future__ import annotations

import webbrowser

LINKS = {
    "discord": "https://discord.gg/hxpuTQF2Bb",
    "telegram": "https://t.me/+NwReoOS9x7hhYjgy",
    "github": "https://github.com/rgeraskin/barrens-voice/issues",
    "rhvoice": "https://rhvoice.su/voices/",
    "silero": "https://github.com/snakers4/silero-models/releases?q=SAPI",
}


def open_link(key: str, log, opener=webbrowser.open) -> str | None:
    """Open the page named `key` in the default browser; its address, or None for a name not known."""
    url = LINKS.get(key.strip())
    if url is None:
        log(f"ссылка «{key.strip()}» неизвестна — не открываю")
        return None
    try:
        opener(url)
        log(f"открываю в браузере: {url}")
    except Exception as e:  # noqa: BLE001 - no browser is not an error of the companion
        log("не удалось открыть браузер")
        log(f"    {e}: {url}")
    return url


def _set_clipboard(text: str) -> None:
    import win32clipboard
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
    finally:
        win32clipboard.CloseClipboard()


def copy_link(key: str, log, setter=_set_clipboard) -> str | None:
    """Put the address named `key` on the clipboard; the address, or None for a name not known."""
    url = LINKS.get(key.strip())
    if url is None:
        log(f"ссылка «{key.strip()}» неизвестна — не копирую")
        return None
    try:
        setter(url)
        log(f"адрес в буфере обмена: {url}")
    except Exception as e:  # noqa: BLE001 - the clipboard held by another program: say so, go on
        log("не удалось положить адрес в буфер обмена")
        log(f"    {e}: {url}")
    return url
