"""Log levels: what a line of the companion's log is about, for the launcher to show each to whom.

Every line goes to the log file and to the launcher with its level ("03:12:01 INFO  окно WoW: ...").
The launcher's main window shows INFO, WARN and ERROR without the level - how the companion is
doing; its log window shows everything. The level comes from the message itself, here, in one table:
the companion's modules log with a plain function (their tests pass list.append), and one place to
change beats a level argument at ninety calls.

DEBUG  details: models loaded, dictionaries, synthesis timing, lines skipped, library notices
CHAT   a chat line read aloud (and how it was read: the indented lines under it are DEBUG)
INFO   the companion's progress: started, the game, the voices ready, the link with the addon
WARN   something the player may need to act on
ERROR  something broke
"""
from __future__ import annotations

import re

LINE = re.compile(r"^(\d\d:\d\d:\d\d) (DEBUG|CHAT|INFO|WARN|ERROR) +(.*)$")

DEBUG_STARTS = (
    "загружаю RUAccent", "загружаю F5-TTS", "F5 (ONNX", "F5-TTS готов на", "словарь", "голосов Windows:",
    "список голосов Windows", "полоска (", "полоска:", "захват окна WoW", "приоритет ниже игры",
    "русских реплик в клиенте", "голосов рас:", "строка ", "строки типа", "адрес в буфере", "открываю в браузере",
    "память:", "файлы:", "модели F5 (ONNX)", "CatQuest говорит", "CatQuest замолчал", "пауза для CatQuest",
    "=", "[диагностика аддона]", "[stderr]", "окно WoW:", "полоска найдена в другом месте", "хранилище ",
    "Battle.net только что запустился", "«Что нового»",
)
WARN_STARTS = (
    "Battle.net не найден", "Battle.net не запустил игру", "папка аддона не найдена", "аддон не найден", "нет ни одного русского голоса",
    "pymorphy3 не установлен", "RUAccent не установлен", "полоска аддона пропала", "полоска видна, но не читается",
    "в кэше моделей не всё", "очередь полна", "Голоса рас недоступны", "игра скачала не все голоса",
    "захват окна недоступен", "Whisper (ONNX) недоступен", "снимок не удался", "не удалось",
    "ссылка «", "аддон новее лаунчера", "аддон старше лаунчера",
    "если окно чата не прячется",       # the /reload reminder (reloadhint): yellow in the launcher's main window
)
ERROR_STARTS = ("ОШИБКА", "F5-TTS:", "RUAccent:", "ошибка голоса", "голоса рас из клиента:")


def level_of(message: str) -> str:
    """The level of a log message (see the module's table)."""
    if message.startswith(" "):                     # the details under a line: how it was read, why, a traceback
        return "DEBUG"
    if message.startswith(ERROR_STARTS):
        return "ERROR"
    if message.startswith(WARN_STARTS):
        return "WARN"
    if message.startswith(DEBUG_STARTS):
        return "DEBUG"
    if message.startswith("[") and "] " in message:   # "[гильдия] Громмаш (Orc, м) → orc-male: ..."
        return "CHAT"
    return "INFO"


ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
INSIDE = re.compile(r"(\d\d:\d\d:\d\d) (DEBUG|CHAT|INFO|WARN|ERROR) +(.*)$")


def clean(text: str) -> str:
    """A raw line as it would look in a console: a bar redrawn with "\\r" - its last state, no colour codes."""
    states = [part for part in ANSI.sub("", text).split("\r") if part.strip()]
    return states[-1].rstrip() if states else ""


def parse(line: str) -> tuple[str, str, str]:
    """(time, level, message) of a log line; a line in no such form (a library's own output) is DEBUG.
    A log line glued to a library's unfinished output (a bar without its line end) is still found."""
    m = LINE.match(line)
    if m:
        return m.group(1), m.group(2), m.group(3)
    m = INSIDE.search(line)
    if m:
        return m.group(1), m.group(2), m.group(3)
    return "", "DEBUG", clean(line)


def raw_line(text: str, now) -> str | None:
    """A line a library wrote straight to the companion's stderr (below Python: onnxruntime, Rust
    downloaders), in the log's form; None when nothing is left of it."""
    text = clean(text)
    return f"{now:%H:%M:%S} DEBUG [stderr] {text}" if text.strip() else None
