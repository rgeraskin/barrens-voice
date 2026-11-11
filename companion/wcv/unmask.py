"""Words written so a chat's swear filter does not catch them, read as the words they are.

Players hide letters of swear words (and sometimes of plain ones): Latin letters that look like
Russian ones ("xyйня", "пuздец"), digits inside a word ("п0шел"), and asterisks for letters
("х*й", "бл*ть"), or other signs for them ("бл@дь", "бл#ть"). A bracket pair for "х" (")(") the
addon already reads back. Latin and digits
are put back only inside a word that is otherwise Russian, and only when every Latin letter has a
Russian twin (so "PvPшник" stays as it is); a word with masking signs is matched against WORDS, the
common swear words in their common forms, most frequent first; "@" that matches none is an "а".
"""
from __future__ import annotations

import re

LATIN = {"a": "а", "e": "е", "o": "о", "p": "р", "c": "с", "x": "х", "y": "у", "k": "к", "u": "и", "m": "м",
         "t": "т", "A": "А", "B": "В", "E": "Е", "K": "К", "M": "М", "H": "Н", "O": "О", "P": "Р", "C": "С",
         "T": "Т", "X": "Х", "Y": "У"}
DIGITS = {"0": "о", "3": "з", "4": "ч", "6": "б"}   # only between letters: "4дд" is four
MASKS = "*@#$%&"                                      # signs standing for hidden letters
TOKEN = re.compile(r"[\w*@#$%&]+")
CYRILLIC = re.compile(r"[а-яёА-ЯЁ]")

WORDS = """
хуй хуя хую хуи хуем хуёв хуев нахуй нахуя похуй похую нихуя дохуя хуйня хуйни хуйню хуйней хуево хуёво
хуевый хуёвый хуевая хуёвая хуевое хуёвое хуевые хуёвые хуета хуеты хуесос хули охуел охуела охуели охуеть
охуенно охуенный охуенная ахуеть ахуенно хуярить хуячить захуярить
пиздец пиздеца пиздецом пизда пизды пизде пизду пиздой пиздеть пиздит пиздишь пиздеж пиздёж пиздато пиздатый
пиздуй пиздуйте спиздил спиздили спиздить отпиздить распиздяй пиздюк
блядь бля блять бляди блядский блядство блядина
ебать ебал ебала ебали ебёт ебет ебаться ебанутый ебанулся ебанись ебаный ёбаный ебаная ебаное ебаные ебучий
ебло еблан ебланы заебал заебала заебали заебало заебись наебал наебали наебнулся уебок уёбок уебище уёбище
уебан выебон выебываться доебался отъебись поебать поебень съебался съебись
сука суки суке суку сукой сучка сучки сучара сукин
мудак мудака мудаки мудаков мудило мудила
пидор пидора пидоры пидорас пидорасы пидр долбоеб долбоёб долбоебы долбоёбы
гандон гондон гандоны гондоны шлюха шлюхи говно говна говном дерьмо дерьма жопа жопы жопу залупа манда
""".split()


def _letters(token: str) -> str:
    """Latin twins and digits inside the word, put back - when the word is Russian otherwise."""
    if not CYRILLIC.search(token):
        return token
    latin = [ch for ch in token if ch.isascii() and ch.isalpha()]
    if latin and not all(ch in LATIN for ch in latin):
        return token
    out = list(token)
    for i, ch in enumerate(token):
        if ch in LATIN:
            out[i] = LATIN[ch]
        elif ch in DIGITS and 0 < i < len(token) - 1 and token[i - 1].isalpha() and token[i + 1].isalpha():
            out[i] = DIGITS[ch]
    return "".join(out)


def _stars(token: str) -> str:
    """A word with masking signs ("х*й", "бл**ь", "бл@дь") as the swear word it hides, if exactly
    that shape fits one; "@" left over is an "а" ("прив@т")."""
    if not any(ch in MASKS for ch in token) or not CYRILLIC.search(token):
        return token
    lower = token.lower().replace("ё", "е")
    pattern = re.compile("^" + "".join(
        f".{{1,{len(run) + 1}}}" if run[0] in MASKS else re.escape(run)
        for run in re.findall(r"[*@#$%&]+|[^*@#$%&]+", lower)) + "$")
    for word in WORDS:
        if pattern.match(word.replace("ё", "е")):
            return word
    return token.replace("@", "а")


def unmask(text: str) -> str:
    return TOKEN.sub(lambda m: _stars(_letters(m.group())), text)
