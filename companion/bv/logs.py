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

LEVELS = ("DEBUG", "CHAT", "INFO", "WARN", "ERROR")
LINE = re.compile(r"^(\d\d:\d\d:\d\d) (DEBUG|CHAT|INFO|WARN|ERROR) +(.*)$")

DEBUG_STARTS = (
    "загружаю RUAccent", "загружаю F5-TTS", "F5 (ONNX", "F5-TTS готов на", "словарь", "голосов Windows:",
    "список голосов Windows", "полоска (по сохранённым", "полоска:", "захват окна WoW", "приоритет ниже игры",
    "русских реплик в клиенте", "голосов рас:", "строка ", "строки типа", "адрес в буфере", "открываю в браузере",
    "память:", "файлы:", "модели F5 (ONNX)", "CatQuest говорит", "CatQuest замолчал", "пауза для CatQuest",
    "=", "[диагностика аддона]", "[stderr]",
)
WARN_STARTS = (
    "Battle.net не найден", "Battle.net не запустил игру", "папка аддона не найдена", "аддон BarrensVoice не найден", "нет ни одного русского голоса",
    "pymorphy3 не установлен", "RUAccent не установлен", "полоска аддона пропала", "полоска видна, но кадры",
    "в кэше моделей чего-то не хватает", "очередь полна", "Голоса рас недоступны", "файлов голосов ещё нет",
    "Windows Graphics Capture недоступен", "Whisper (ONNX) недоступен", "снимок не удался", "не удалось",
    "ссылка «",
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


def parse(line: str) -> tuple[str, str, str]:
    """(time, level, message) of a log line; a line in no such form (a library's own output) is DEBUG."""
    m = LINE.match(line)
    if m:
        return m.group(1), m.group(2), m.group(3)
    return "", "DEBUG", line
