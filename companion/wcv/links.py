"""Pages the addon asks the companion to open in the browser (a click in its settings: an addon
cannot open a browser - LaunchURL is Blizzard's own). The addon sends only a name; only the
addresses here are ever opened, the same as the addon's ns.LINKS (Core.lua)."""
from __future__ import annotations

import webbrowser

LINKS = {
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
        log(f"не удалось открыть браузер ({e}): {url}")
    return url
