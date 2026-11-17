"""Text before speech: stress marks (RUAccent, the dictionary's own marks kept), numbers as words,
and stress marks in the form each engine takes."""
from __future__ import annotations

import os
import re
import threading
from pathlib import Path

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
# "ги-бэ-дэ-д+э"), read as a word when it can ("ОМОН", "ВУЗ").
CAPITALS = re.compile(r"\b[А-ЯЁ]{2,5}\b")
VOWELS = set("АЕЁИОУЫЭЮЯ")
LETTERS = {"Б": "бэ", "В": "вэ", "Г": "гэ", "Д": "дэ", "Ж": "жэ", "З": "зэ", "Й": "йот", "К": "ка", "Л": "эл",
           "М": "эм", "Н": "эн", "П": "пэ", "Р": "эр", "С": "эс", "Т": "тэ", "Ф": "эф", "Х": "ха", "Ц": "цэ",
           "Ч": "чэ", "Ш": "ша", "Щ": "ща", "Ъ": "твёрдый знак", "Ь": "мягкий знак"}


def spell(abbreviation: str) -> str:
    """Letter by letter, the last letter's name stressed: "МВД" - "эм-вэ-д+э" (the "+" goes before a
    vowel, the only place `apply_stress` takes it from: "+дэ" reached the voices as a plain "+")."""
    names = [LETTERS.get(ch, ch.lower()) for ch in abbreviation]
    last = names[-1]
    vowel = next((i for i, ch in enumerate(last) if ch.upper() in VOWELS), None)
    if vowel is not None:
        names[-1] = last[:vowel] + "+" + last[vowel:]
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
    morph = analyzer()
    if morph is not None and morph.word_is_known(word.lower()) and \
            not any("Abbr" in p.tag for p in morph.parse(word.lower())):
        return word.lower()                            # a word written in capitals
    if not unpronounceable(word):
        return word
    vowel = [ch in VOWELS for ch in word]
    if len(word) > 2 and not vowel[0] and vowel[1]:
        return word[:2].lower() + "-" + spell(word[2:])   # a syllable to begin with: "ГИБДД" - "ги-бэ-дэ-д+э"
    return spell(word)


EMOJI_CODE = re.compile(r"(?<![\w:]):[a-z][a-z0-9_+-]*:(?![\w:])")   # ":handshake:" (Discord's): not read out


def plain(text: str) -> str:
    """Text as it is said: a quest level tag ("[24]" before a quest name) and a quest's number at the
    end of its name ("(3513)]", as quest addons write it) go, other brackets left
    over become spaces - they also glued the word before them to the next ("с[Разыскивается"); a word in capitals of 4
    letters or more is lowered, or RUAccent stresses it as an abbreviation ("РАЗ+ЫСКИВАЕТСЯ"); an
    abbreviation the dictionary did not expand is spelt when it cannot be said as syllables ("ППС" -
    "пэ-пэ-+эс", "США"), see `_capitals`."""
    text = EMOJI_CODE.sub(" ", BRACKETS.sub(" ", LEVEL_TAG.sub(" ", QUEST_ID.sub("", text))))
    text = SHOUTED.sub(lambda m: m.group().lower(), CAPITALS.sub(_capitals, text))
    return re.sub(r"\s+([,.!?:;…])", r"\1", re.sub(r"\s{2,}", " ", text)).strip()


# the word after a number, hyphenated ones whole: "5 рейд-лидеров" agrees with "лидеров", its last part
NEXT_WORD = re.compile(r"\s+([а-яёА-ЯЁ+]+(?:-[а-яёА-ЯЁ+]+)*)")
GENDERS = {"masc", "femn", "neut"}
# words that number rather than count: "15 уровня" is the fifteenth (a count is "15 уровней")
NUMBERED = {"уровень", "этаж", "число", "ранг", "фаза", "сезон", "глава", "акт", "волна", "слот", "босс"}
# a numbered noun whose singular the stress model takes for the plural ("числ+а" - "two numbers"):
# after an ordinal it is the singular, stressed here
SINGULAR_STRESS = {"числа": "ч+исла"}
# a number that goes on from the one before it - a time, a decimal, a version: neither an ordinal nor agreeing
GLUED = re.compile(r"\d[:.,]$")
GOES_ON = re.compile(r"[:.,]\d")       # ... and a number with one after it: "до 20:00" is a time, not a count
PREV_WORD = re.compile(r"(?<![\w'+-])([а-яёА-ЯЁ]+(?:-[а-яёА-ЯЁ]+)?)\s+$")   # a whole word, as morph.PREVIOUS
# the cases a preposition asks of the word after it (only those a count never takes in the singular);
# "нет" is no preposition but asks the genitive the same way ("нет 5 места", "нет 5 игроков")
GOVERNS = {**dict.fromkeys(("с", "со"), {"gent", "ablt"}),
           **dict.fromkeys(("до", "от", "из", "для", "без", "после", "около", "у", "кроме", "из-за", "из-под", "нет"), {"gent"}),
           **dict.fromkeys(("к", "ко", "по"), {"datv"}),
           **dict.fromkeys(("в", "во", "на", "о", "об", "при"), {"loct"}),
           **dict.fromkeys(("за", "под", "над", "перед"), {"ablt"})}
OBLIQUE = {"gent", "datv", "ablt", "loct"}
_morph = None
_morph_lock = threading.Lock()


def analyzer():
    """pymorphy3's analyzer, loaded once (None without pymorphy3) and shared: the numbers here and the
    declension (morph.Inflector) - each one is about 24 MB."""
    global _morph
    with _morph_lock:
        if _morph is None:
            try:
                import pymorphy3
                _morph = pymorphy3.MorphAnalyzer()
            except ImportError:
                _morph = False
    return _morph or None


def to_case(words: list[str], case: str, morph) -> list[str]:
    """Number words in `case`, as a numeral where pymorphy has one ("сто" - "ста", not the
    abbreviation "СТО", which it lists first)."""
    out = []
    for w in words:
        parses = morph.parse(w)
        parse = next((p for p in parses if p.tag.POS == "NUMR"), parses[0])
        form = parse.inflect({case})
        out.append(form.word if form else w)
    return out


def agree(n: int, spoken: str, following: str, morph, before: str = "") -> str:
    """`spoken` (num2words' nominative for `n`) agreeing with the word after it:
    "1 руку" -> "одну", "без 1 руки" -> "одной", "2 руки" -> "две", "с 5 магами" -> "пятью";
    `before`, the word before the number, gives the genitive, which the word alone cannot ("5 игроков"
    is also the nominative count): "у 5 игроков" - "пяти", "до 200 опыта" - "двухсот".
    Left as it is when the word is not a noun or adjective, not in pymorphy's dictionary (slang:
    "2 дамагера"), or could be the plain nominative ("1 золотой")."""
    word = following.replace("+", "").lower()
    asked = GOVERNS.get(before.lower(), set())
    parts = spoken.split()
    one = n % 10 == 1 and not 10 < n % 100 < 20
    if "gent" in asked and word == "до":
        return " ".join(to_case(parts, "gent", morph))  # a range: "с 5 до 10" - "с пяти до десяти"
    if asked == {"gent"} and not one:
        # a count after a preposition that asks only the genitive is in the genitive whatever word
        # follows ("ordinal" has had its say): "из-за 2 боссов", "до 200 опыта", slang "для 3 хилов"
        return " ".join(to_case(parts, "gent", morph))
    if not morph.word_is_known(word):
        return spoken                                  # a guess ("дамагера" as feminine) does worse
    parses = [p for p in morph.parse(word) if p.tag.POS in ("NOUN", "ADJF", "PRTF")]
    if not parses:
        return spoken
    if one:
        sing = [p for p in parses if p.tag.number == "sing"]
        if not sing or any(p.tag.case == "nomn" and p.tag.gender in ("masc", None) for p in sing):
            return spoken
        # the case the preposition asks first: "у 101 игрока" - "ста одного" (not the accusative)
        tag = next((p.tag for p in sing if p.tag.case in asked), sing[0].tag)
        tags = {tag.case} | ({tag.gender} if tag.gender in GENDERS else set())
        if tag.case == "accs" and tag.gender == "masc" and tag.animacy:
            tags.add(tag.animacy)                      # "на 1 мага" - "одного"
        one = morph.parse("один")[0].inflect(tags)
        if one:
            parts[-1] = one.word
        if tag.case in OBLIQUE:                        # "с 21 магом" - "двадцатью одним"
            parts[:-1] = to_case(parts[:-1], tag.case, morph)
        return " ".join(parts)
    if "gent" in asked and any(p.tag.case == "gent" for p in parses):
        return " ".join(to_case(parts, "gent", morph))  # "с 5 часов" - "пяти" ("с 5 магами" - "пятью" below)
    tag = parses[0].tag
    if tag.number == "plur" and tag.case in ("datv", "ablt", "loct"):
        return " ".join(to_case(parts, tag.case, morph))  # "в 3 сумках" - "трёх"
    if n % 10 == 2 and n % 100 != 12 and parts[-1] == "два" and tag.gender == "femn":
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


# "+" and "-" typed after a number: the addon says "+" as the word "плюс" ("50+ лвл" - "50 плюс лвл"),
# which is not a noun the number counts or numbers ("пятидесятый плюс"): a cardinal, in the preposition's case
SIGNS = {"плюс", "минус"}
# an ordinal's ending glued to its number: "40го", "2007-го", "на 4м этаже" - the ordinal in that form
ENDING = re.compile(r"-?(ого|его|ому|ему|ыми|ими|ым|им|ом|ем|ый|ий|ой|ая|яя|ое|ее|ую|юю|ых|их|ые|ие|ух|ех|го|му|м|й|я|е|ю|х)"
                    r"(?![а-яёa-z])", re.IGNORECASE)
LETTERS_AFTER = re.compile(r"[а-яёa-z]{2,}", re.IGNORECASE)   # "200ХП": letters glued to a number, read apart
# "идём в 4м" (and no noun after it): together, so many of us - not "в четвёртом"
TOGETHER = re.compile(r"\b([вВ])\s*([2-9]|10)\s*-?м\b(?!\s*[а-яёa-z])")
COLLECTIVE = {2: "двоём", 3: "троём", 4: "четвером", 5: "пятером", 6: "шестером", 7: "семером", 8: "восьмером",
              9: "девятером", 10: "десятером"}


def ending_form(n: int, ending: str, before: str, morph) -> str | None:
    """`n` as the ordinal whose form ends in `ending` ("40го" - "сорокового"), the case the preposition
    before it asks for preferred ("в 4м" - "четвёртом", "с 4м" - "четвёртым"); None when none ends so."""
    from num2words import num2words
    parts = num2words(n, lang="ru", to="ordinal").split()
    asked = GOVERNS.get(before.lower(), set()) | ({"accs"} if before.lower() in ("в", "во", "на", "за", "про") else set())
    forms = [f for f in morph.parse(parts[-1])[0].lexeme if f.word.endswith(ending.lower())]
    if not forms:
        return None
    best = next((f for f in forms if f.tag.case in asked), forms[0])
    parts[-1] = best.word
    return " ".join(parts)


def numbers_to_words(text: str) -> str:
    """Digits as Russian words, agreeing with the word after them where pymorphy3 can tell how."""
    try:
        from num2words import num2words
    except ImportError:
        return text
    morph = analyzer()
    text = TOGETHER.sub(lambda m: m.group(1) + COLLECTIVE[int(m.group(2))], text)

    def spell(m) -> tuple[str, int]:
        """The number in words, and where the text it stands for ends (past the word after it
        when that word's stress is settled here too)."""
        if len(m.group()) >= 10:
            return m.group(), m.end()
        n = int(m.group())
        spoken = num2words(n, lang="ru")
        before = PREV_WORD.search(m.string, 0, m.start())
        before = before.group(1) if before else ""
        glued = ENDING.match(m.string, m.end())
        if glued and morph is not None:
            ending = glued.group(1).lower()
            if ending in ("х", "ух", "ех"):              # "из 2х", "3х": a count in the genitive - "двух", "трёх"
                return " ".join(to_case(spoken.split(), "gent", morph)), glued.end()
            # a lone "м" is an ordinal only after a preposition ("на 4м этаже"); "через 5м" is minutes or metres
            if ending != "м" or before.lower() in GOVERNS:
                as_ordinal = ending_form(n, glued.group(1), before, morph)
                if as_ordinal:
                    return as_ordinal, glued.end()
        if LETTERS_AFTER.match(m.string, m.end()):
            return spoken + " ", m.end()                # "200ХП" - "двести ХП"
        following = NEXT_WORD.match(m.string, m.end())
        if GLUED.search(m.string, 0, m.start()):
            following = None                           # "20:00 сбор", "1.12 патч": no "нулевой сбор"
        if morph is not None and following and following.group(1).lower() in SIGNS:
            # "от 50+" - "от пятидесяти плюс"; "на 3+ человек" stays "на три плюс" (the accusative)
            case = "gent" if "gent" in GOVERNS.get(before.lower(), set()) else None
            if case:
                spoken = " ".join(to_case(spoken.split(), case, morph))
            return spoken, m.end()
        if morph is not None and following:
            head = following.group(1).rsplit("-", 1)[-1]
            try:
                as_ordinal = ordinal(n, before, head, morph)
                if as_ordinal:
                    word = following.group(1)
                    stressed = SINGULAR_STRESS.get(word.lower())
                    if stressed:                       # "одиннадцатого ч+исла", not the plural "числ+а"
                        stressed = word[0] + stressed[1:]
                        return as_ordinal + m.string[m.end():following.start(1)] + stressed, following.end(1)
                    return as_ordinal, m.end()
                spoken = agree(n, spoken, head, morph, before)
            except Exception:  # noqa: BLE001 - a number read in the nominative is still a number
                pass
        elif (morph is not None and GOVERNS.get(before.lower()) == {"gent"}
              and not GOES_ON.match(m.string, m.end())):
            spoken = " ".join(to_case(spoken.split(), "gent", morph))   # "ждём до 10." - "до десяти"
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


def ruaccent_dir() -> Path:
    """Where RUAccent keeps its dictionary and models: in the model cache (HF_HOME, set by main), not in
    its own package folder - its default, which a new Python environment (an update, the installer)
    starts without, and then RUAccent asks the hub even with the cache marked complete (offline)."""
    return Path(os.environ.get("HF_HOME") or Path.home() / ".cache" / "huggingface") / "ruaccent"


def keep_koziev(package: str | None, before: bool) -> None:
    """RUAccent puts one model, `koziev`, into its own package folder whatever `workdir` says: a new
    environment lacks it and RUAccent goes online for it. So a copy lives in `ruaccent_dir` too:
    put back into the package before loading, saved from it after."""
    import shutil
    if package is None:
        import importlib.util
        spec = importlib.util.find_spec("ruaccent")
        if spec is None or not spec.origin:
            return
        package = str(Path(spec.origin).parent)
    inside, kept = Path(package) / "koziev", ruaccent_dir() / "koziev"
    try:
        if before and not inside.exists() and kept.is_dir():
            shutil.copytree(kept, inside)
        elif not before and inside.is_dir() and not kept.exists():
            shutil.copytree(inside, kept)
    except OSError:
        pass                                        # RUAccent goes online for it, as before


class Accentor:
    """RUAccent, loaded on first use (about 10 s; its files in `ruaccent_dir`)."""

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
        keep_koziev(model.module_path if hasattr(model, "module_path") else None, before=True)
        model.load(omograph_model_size="turbo3.1", use_dictionary=True, tiny_mode=False, workdir=str(ruaccent_dir()))
        keep_koziev(getattr(model, "module_path", None), before=False)
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
