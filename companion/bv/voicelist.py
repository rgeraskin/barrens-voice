"""The Windows voices, written into the addon as VoiceList.lua, so the addon can offer them (it
cannot ask Windows itself, and the program cannot talk to the game). WoW reads the file at start
and on /reload."""
from __future__ import annotations

from pathlib import Path

from .dictionary import GAMES, game_of, wow_roots

ENGINES = {"edge": "Edge", "rhvoice": "RHVoice", "silero": "Silero", "other": "Windows"}


def find_addon(config: dict) -> Path | None:
    for root in wow_roots(config):
        path = root / "Interface" / "AddOns" / "BarrensVoice"
        if (path / "BarrensVoice.toc").exists():
            return path
    return None


def missing_addon(config: dict) -> str | None:
    """Why the companion cannot work without the addon, in words for the player - or None when the
    addon is there. Without it nothing reaches the companion: it stops at once instead of launching
    the game and waiting for a strip that never comes."""
    if find_addon(config):
        return None
    games = [str(r) for r in wow_roots(config) if (r / "Interface").is_dir() or (r / "Wow.exe").exists()]
    where = ("в папке игры " + ", ".join(games)) if games else "— папка игры тоже не найдена"
    return ("аддон Barrens Voice не установлен: нет Interface\\AddOns\\BarrensVoice\\BarrensVoice.toc " + where + ". "
            "Скопируйте папку addon\\BarrensVoice в World of Warcraft\\" + GAMES[game_of(config)] + "\\Interface\\AddOns\\ "
            "(или укажите wow_dir в config.json, если игра стоит в другом месте) и запустите компаньон снова.")


def label(voice) -> str:
    name = voice.description
    for cut in (" - Russian (Russia)", " Online (Natural)", " (Russian)", " - Russian"):
        name = name.replace(cut, "")
    name = name.removeprefix("Microsoft ")
    return f"{name} ({ENGINES.get(voice.engine, voice.engine)})"


def _lua(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render(voices, default_off) -> str:
    rows = [f"    {{ name = {_lua(v.description)}, label = {_lua(label(v))}, gender = {_lua(v.gender)}, "
            f"on = {'false' if default_off(v) else 'true'} }}," for v in voices]
    return ("-- Written by the Barrens Voice program: the Windows voices it can speak with.\n"
            "BarrensVoiceVoiceList = {\n" + "\n".join(rows) + "\n}\n")


def write(config: dict, voices, default_off, log) -> None:
    addon = find_addon(config)
    if addon is None:
        log("аддон BarrensVoice не найден: список голосов для него не записан")
        return
    path = addon / "VoiceList.lua"
    text = render(voices, default_off)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return
    path.write_text(text, encoding="utf-8")
    log(f"список голосов Windows записан в аддон ({len(voices)}); в игре он появится после /reload")
