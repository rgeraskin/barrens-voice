"""Text before speech: stress marks (RUAccent, the dictionary's own marks kept), numbers as words,
and stress marks in the form each engine takes."""
from __future__ import annotations

import re
import threading

STRESS = re.compile(r"\+([аеёиоуыэюяАЕЁИОУЫЭЮЯ])")
WORD = re.compile(r"[\w+]+")
CYRILLIC = re.compile(r"[а-яёА-ЯЁ]")
NUMBER = re.compile(r"\d+")


def apply_stress(text: str, mode: str) -> str:
    """Stress marks written as "+" before a vowel, as an engine takes them: "plus" keeps them,
    "acute" puts U+0301 after the vowel, "strip" removes them."""
    if mode == "plus":
        return text
    if mode == "acute":
        return STRESS.sub(lambda m: m.group(1) + "́", text)
    return STRESS.sub(r"\1", text)


def merge_marks(original: str, accented: str) -> str:
    """`original` with the stress marks RUAccent put in `accented` (its output for `original`
    without the "+"), word by word; the words that already had a "+" in `original` keep theirs
    (the dictionary's marks win). The words are matched by their letters, like a diff, so a
    different split ("RU/UA", "<MIR>", a hyphen) loses the marks of those words only - it used to
    lose the whole line's, and F5 then guessed every stress ("игр+оков"). The text itself comes
    from `original`: RUAccent's spacing changes (it glued "с[") never reach the speech."""
    import difflib

    words = list(WORD.finditer(original))
    marked = WORD.findall(accented)
    plain = [w.group().replace("+", "").lower() for w in words]
    heard = [w.replace("+", "").lower() for w in marked]
    out, last = [], 0
    matcher = difflib.SequenceMatcher(None, plain, heard, autojunk=False)
    pairs = {i: j for a, b, n in matcher.get_matching_blocks() for i, j in zip(range(a, a + n), range(b, b + n))}
    for i, w in enumerate(words):
        out.append(original[last:w.start()])
        word = w.group()
        if "+" not in word and i in pairs:
            word = _with_marks(word, marked[pairs[i]])
        out.append(word)
        last = w.end()
    out.append(original[last:])
    return "".join(out)


def _with_marks(word: str, marked: str) -> str:
    """`word` with a "+" where `marked` (the same letters) has one - `word`'s own letter case kept."""
    out, k = [], 0
    for ch in marked:
        if ch == "+":
            out.append("+")
        else:
            out.append(word[k])
            k += 1
    return "".join(out)


LEVEL_TAG = re.compile(r"\[\d+[^\]\s]{0,3}\]")   # "[24]", "[60+]", "[23D]" before a quest name (Questie & co)
BRACKETS = re.compile(r"[\[\]{}]")
QUEST_ID = re.compile(r"\s*\(\d+\)(?=\s*\])")   # "[[25] Свиток с рунами (3513)]": the quest's number in the database
SHOUTED = re.compile(r"\b[А-ЯЁ]{4,}\b")
# A word in capitals of 2-5 letters the dictionary did not expand: a word shouted ("ВСЁ", "СТОЙ")
# when pymorphy knows it as one, else an abbreviation - spelt when it cannot be said as syllables
# ("ППС" - "пэ-пэ-+эс", "МВД", "ЦРУ", "США"; a syllable to begin with is said as one: "ГИБДД" -
# "ги-бэ-дэ-+дэ"), read as a word when it can ("ОМОН", "ВУЗ").
CAPITALS = re.compile(r"\b[А-ЯЁ]{2,5}\b")
VOWELS = set("АЕЁИОУЫЭЮЯ")
LETTERS = {"Б": "бэ", "В": "вэ", "Г": "гэ", "Д": "дэ", "Ж": "жэ", "З": "зэ", "Й": "йот", "К": "ка", "Л": "эл",
           "М": "эм", "Н": "эн", "П": "пэ", "Р": "эр", "С": "эс", "Т": "тэ", "Ф": "эф", "Х": "ха", "Ц": "цэ",
           "Ч": "чэ", "Ш": "ша", "Щ": "ща", "Ъ": "твёрдый знак", "Ь": "мягкий знак"}


def spell(abbreviation: str) -> str:
    names = [LETTERS.get(ch, ch.lower()) for ch in abbreviation]
    names[-1] = "+" + names[-1]
    return "-".join(names)


def unpronounceable(word: str) -> bool:
    """Capitals that cannot be said as syllables: no vowel, two consonants to begin with, three in a
    row anywhere, or two at the end of a short one ("АХК") - read letter by letter in Russian."""
    consonant = [ch not in VOWELS for ch in word]
    runs = "".join("c" if c else "v" for c in consonant)
    return ("v" not in runs or runs.startswith("cc") or "ccc" in runs
            or (len(word) <= 3 and runs.endswith("cc")))


def _capitals(match) -> str:
    word = match.group()
    morph = _analyzer()
    if morph is not None and morph.word_is_known(word.lower()) and \
            not any("Abbr" in p.tag for p in morph.parse(word.lower())):
        return word.lower()                            # a word written in capitals
    if not unpronounceable(word):
        return word
    vowel = [ch in VOWELS for ch in word]
    if len(word) > 2 and not vowel[0] and vowel[1]:
        return word[:2].lower() + "-" + spell(word[2:])   # a syllable to begin with: "ГИБДД" - "ги-бэ-дэ-+дэ"
    return spell(word)


def plain(text: str) -> str:
    """Text as it is said: a quest level tag ("[24]" before a quest name) and a quest's number at the
    end of its name ("(3513)]", as quest addons write it) go, other brackets left
    over become spaces - they also glued the word before them to the next ("с[Разыскивается"); a word in capitals of 4
    letters or more is lowered, or RUAccent stresses it as an abbreviation ("РАЗ+ЫСКИВАЕТСЯ"); an
    abbreviation the dictionary did not expand is spelt when it cannot be said as syllables ("ППС" -
    "пэ-пэ-+эс", "США"), see `_capitals`."""
    text = BRACKETS.sub(" ", LEVEL_TAG.sub(" ", QUEST_ID.sub("", text)))
    text = SHOUTED.sub(lambda m: m.group().lower(), CAPITALS.sub(_capitals, text))
    return re.sub(r"\s+([,.!?:;…])", r"\1", re.sub(r"\s{2,}", " ", text)).strip()


NEXT_WORD = re.compile(r"\s+([а-яёА-ЯЁ+]+)")
GENDERS = {"masc", "femn", "neut"}
# words that number rather than count: "15 уровня" is the fifteenth (a count is "15 уровней")
NUMBERED = {"уровень", "этаж", "число", "ранг", "фаза", "сезон", "глава", "акт", "волна", "слот", "босс"}
# a numbered noun whose singular the stress model takes for the plural ("числ+а" - "two numbers"):
# after an ordinal it is the singular, stressed here
SINGULAR_STRESS = {"числа": "ч+исла", "места": "м+еста"}
PREV_WORD = re.compile(r"([а-яёА-ЯЁ]+)\s+$")
# the cases a preposition asks of the word after it (only those a count never takes in the singular)
GOVERNS = {**dict.fromkeys(("с", "со"), {"gent", "ablt"}),
           **dict.fromkeys(("до", "от", "из", "для", "без", "после", "около", "у", "кроме"), {"gent"}),
           **dict.fromkeys(("к", "ко", "по"), {"datv"}),
           **dict.fromkeys(("в", "во", "на", "о", "об", "при"), {"loct"}),
           **dict.fromkeys(("за", "под", "над", "перед"), {"ablt"})}
OBLIQUE = {"gent", "datv", "ablt", "loct"}
_morph = None
_morph_lock = threading.Lock()


def _analyzer():
    """pymorphy3's analyzer, loaded once (None without pymorphy3)."""
    global _morph
    with _morph_lock:
        if _morph is None:
            try:
                import pymorphy3
                _morph = pymorphy3.MorphAnalyzer()
            except ImportError:
                _morph = False
    return _morph or None


def agree(n: int, spoken: str, following: str, morph) -> str:
    """`spoken` (num2words' nominative for `n`) agreeing with the word after it:
    "1 руку" -> "одну", "без 1 руки" -> "одной", "2 руки" -> "две", "с 5 магами" -> "пятью".
    Left as it is when the word is not a noun or adjective, not in pymorphy's dictionary (slang:
    "2 дамагера"), or could be the plain nominative ("1 золотой")."""
    word = following.replace("+", "").lower()
    if not morph.word_is_known(word):
        return spoken                                  # a guess ("дамагера" as feminine) does worse
    parses = [p for p in morph.parse(word) if p.tag.POS in ("NOUN", "ADJF", "PRTF")]
    if not parses:
        return spoken
    parts = spoken.split()

    def to_case(words, case):
        out = []
        for w in words:
            form = morph.parse(w)[0].inflect({case})
            out.append(form.word if form else w)
        return out

    teen = 10 < n % 100 < 20
    if n % 10 == 1 and not teen:
        sing = [p for p in parses if p.tag.number == "sing"]
        if not sing or any(p.tag.case == "nomn" and p.tag.gender in ("masc", None) for p in sing):
            return spoken
        tag = sing[0].tag
        tags = {tag.case} | ({tag.gender} if tag.gender in GENDERS else set())
        if tag.case == "accs" and tag.gender == "masc" and tag.animacy:
            tags.add(tag.animacy)                      # "на 1 мага" - "одного"
        one = morph.parse("один")[0].inflect(tags)
        if one:
            parts[-1] = one.word
        if tag.case in OBLIQUE:                        # "с 21 магом" - "двадцатью одним"
            parts[:-1] = to_case(parts[:-1], tag.case)
        return " ".join(parts)
    tag = parses[0].tag
    if tag.number == "plur" and tag.case in ("datv", "ablt", "loct"):
        return " ".join(to_case(parts, tag.case))       # "в 3 сумках" - "трёх"
    if n % 10 == 2 and not teen and parts[-1] == "два" and tag.gender == "femn":
        parts[-1] = "две"                              # "2 руки" - "две"
    return " ".join(parts)


def ordinal(n: int, before: str, following: str, morph) -> str | None:
    """`n` as an ordinal agreeing with the word after it, when only an ordinal fits the phrase:
    "с 15 уровня" -> "пятнадцатого", "на 2 этаже" -> "втором", "15 уровень" -> "пятнадцатый"
    (a count wants a plural there: "15 уровней"); None when a count may be meant ("200 опыта" -
    "сколько", "за 2 часа", "5 раз", slang pymorphy does not know).
    A word that numbers rather than counts (NUMBERED) settles what the grammar leaves open: after
    a number ending in 1 ("с 21 уровня" - "двадцать первого", where "по 1 золотому" stays "одному")
    and in the genitive without a preposition ("хил 15 уровня", where "200 опыта" stays "двести")."""
    from num2words import num2words
    word = following.replace("+", "").lower()
    if not morph.word_is_known(word):
        return None
    parses = [p for p in morph.parse(word) if p.tag.POS == "NOUN"]
    numbered = any(p.normal_form in NUMBERED for p in parses)
    if numbered:
        parses = [p for p in parses if p.tag.number == "sing"]   # "с 3 фазы", not "3 фазы" (plural)
    elif any(p.tag.number != "sing" for p in parses):
        return None
    if not parses:
        return None
    if n % 10 == 1 and n % 100 != 11 and not numbered:
        return None                                    # "по 1 золотому", "без 1 руки": a count reads so too
    asked = GOVERNS.get(before.lower(), set())
    few = 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14
    if any(p.tag.case == "nomn" for p in parses):
        tag = next(p.tag for p in parses if p.tag.case == "nomn")
    elif any(p.tag.case in asked for p in parses):     # the case the preposition asks for
        tag = next(p.tag for p in parses if p.tag.case in asked)
    elif numbered and not few:                         # "на 2 уровня выше" is still two of them
        tag = parses[0].tag
    else:
        return None
    parts = num2words(n, lang="ru", to="ordinal").split()
    form = morph.parse(parts[-1])[0].inflect({tag.case, tag.gender or "masc", "sing"})
    if not form:
        return None
    parts[-1] = form.word
    return " ".join(parts)


def numbers_to_words(text: str) -> str:
    """Digits as Russian words, agreeing with the word after them where pymorphy3 can tell how."""
    try:
        from num2words import num2words
    except ImportError:
        return text
    morph = _analyzer()

    def spell(m) -> tuple[str, int]:
        """The number in words, and where the text it stands for ends (past the word after it
        when that word's stress is settled here too)."""
        if len(m.group()) >= 10:
            return m.group(), m.end()
        n = int(m.group())
        spoken = num2words(n, lang="ru")
        following = NEXT_WORD.match(m.string, m.end())
        if morph is not None and following:
            before = PREV_WORD.search(m.string, 0, m.start())
            try:
                as_ordinal = ordinal(n, before.group(1) if before else "", following.group(1), morph)
                if as_ordinal:
                    word = following.group(1)
                    stressed = SINGULAR_STRESS.get(word.lower())
                    if stressed:                       # "одиннадцатого ч+исла", not the plural "числ+а"
                        stressed = word[0] + stressed[1:]
                        return as_ordinal + m.string[m.end():following.start(1)] + stressed, following.end(1)
                    return as_ordinal, m.end()
                spoken = agree(n, spoken, following.group(1), morph)
            except Exception:  # noqa: BLE001 - a number read in the nominative is still a number
                pass
        return spoken, m.end()

    out, pos = [], 0
    for m in NUMBER.finditer(text):
        if m.start() < pos:
            continue                                   # inside a word taken with the number before
        spoken, end = spell(m)
        out += [text[pos:m.start()], spoken]
        pos = end
    out.append(text[pos:])
    return "".join(out)


class Accentor:
    """RUAccent, loaded on first use (about 10 s; the models are cached by Hugging Face)."""

    def __init__(self, log, enabled: bool = True):
        self.log, self.enabled, self.model = log, enabled, None
        self.lock = threading.Lock()   # shared by the engines' threads

    def load(self) -> None:
        with self.lock:
            self._load()

    def _load(self) -> None:
        if not self.enabled or self.model is not None:
            return
        try:
            import numpy as np
            from ruaccent import RUAccent
        except ImportError:
            self.log("RUAccent не установлен: ударения только из словаря")
            self.enabled = False
            return
        model = RUAccent()
        model.load(omograph_model_size="turbo3.1", use_dictionary=True, tiny_mode=False)
        # This ruaccent does not feed token_type_ids, which its downloaded ONNX models want: zeros.
        for part in vars(model).values():
            session = getattr(part, "session", None)
            if session is None or "token_type_ids" not in {i.name for i in session.get_inputs()}:
                continue

            def run(outputs, feed, *a, _run=session.run, **k):
                if "token_type_ids" not in feed and "input_ids" in feed:
                    feed = dict(feed)
                    feed["token_type_ids"] = np.zeros_like(feed["input_ids"])
                return _run(outputs, feed, *a, **k)

            session.run = run
        self.model = model

    def accent(self, text: str) -> str:
        """`text` with "+" before each stressed vowel; words marked by the dictionary kept."""
        if not self.enabled or not CYRILLIC.search(text):
            return text
        self.load()
        if self.model is None:
            return text
        try:
            with self.lock:
                accented = self.model.process_all(text.replace("+", ""))
        except Exception as e:  # noqa: BLE001 - never lose a line over stress marks
            self.log(f"RUAccent: {e}")
            return text
        return merge_marks(text, accented)
