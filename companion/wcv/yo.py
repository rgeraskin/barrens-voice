"""The letter «ё» where the chat typed «е» (hardly anyone types «ё»): «ждем» -> «ждём», «утес» -> «утёс».

RUAccent puts stress marks but leaves «е» as it is, and a voice reads «ждем» with «е». The words come
from the "safe" dictionary of eyo-kernel (yo_safe.txt, MIT, its notice at the top of the file): about
107 thousand word forms in which «е» can only be «ё». Words where both are words («все»/«всё»,
«берет»/«берёт») are not in it and stay as typed; the slang dictionary can still say them.

The dictionary is read the way eyo-kernel reads it (src/dictionary.ts): a line is a word or a stem
with endings, «берёз(а|ы|е)»; a word in lower case fits a capitalised one too, «_» before it means
lower case only («Киев» the city, «киёв» the cues), a capitalised one is a name and fits only so.
Words with a stress mark ("+", put by the dictionary) are left alone: the dictionary has said them.
"""
from __future__ import annotations

import re
import threading
from pathlib import Path

FILE = Path(__file__).with_name("yo_safe.txt")
WORD = re.compile(r"[А-Яа-яЁё+]+")

_table: dict[str, str] | None = None
_lock = threading.Lock()


def _forms(line: str) -> list[str]:
    """«берёз(а|ы)» -> ["берёза", "берёзы"]; a line without endings is the word itself."""
    line = line.split("#", 1)[0].strip()
    if not line:
        return []
    if "(" not in line:
        return [line]
    parts = re.split(r"[(|)]", line)
    return [parts[0] + ending for ending in parts[1:-1]]


def _plain(word: str) -> str:
    return word.replace("ё", "е").replace("Ё", "Е")


def load(path: Path = FILE) -> dict[str, str]:
    """{the word with «е»: with «ё»}, lower-case and capitalised keys, as eyo-kernel builds it."""
    table: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            continue
        for word in _forms(line):
            lower_only = word.startswith("_")
            word = word.lstrip("_")
            if not word:
                continue
            table[_plain(word)] = word
            if not lower_only and word[0].islower():
                capital = word[0].upper() + word[1:]
                table[_plain(capital)] = capital
    return table


def table() -> dict[str, str]:
    global _table
    if _table is None:
        with _lock:
            if _table is None:
                _table = load()
    return _table


def restore(text: str) -> str:
    """`text` with «ё» in each word the dictionary is sure of; the letter case typed is kept."""
    words = table()

    def fix(m: re.Match) -> str:
        word = m.group(0)
        if "+" in word or ("е" not in word and "Е" not in word):
            return word
        found = words.get(word)
        if found:
            return found
        if len(word) > 1 and word.isupper():               # «ЖДЕМ»: as the word in lower case, in capitals
            found = words.get(word.lower()) or words.get(word[0] + word[1:].lower())
            return found.upper() if found else word
        return word

    return WORD.sub(fix, text)
