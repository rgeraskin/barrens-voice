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


# ":handshake:" (Discord's): not read out; ":+1:" comes from the addon as ": плюс 1:"
EMOJI_CODE = re.compile(r"(?<![\w:]):(?:[a-z][a-z0-9_+-]*|\s*плюс\s*1\s*|-1):(?![\w:])")


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
# a noun whose singular the stress model may take for the plural ("числ+а", "мест+а" - "two of them"):
# after an ordinal it is the singular, stressed here ("до пятнадцатого м+еста")
SINGULAR_STRESS = {"числа": "ч+исла", "места": "м+еста"}
# a number that goes on from the one before it - a time, a decimal, a version: neither an ordinal nor agreeing
GLUED = re.compile(r"\d[:.,]$")
# "2 на 2" (an arena: the dictionary's "2х2"), "10 на 10": a size, both numbers cardinals - not "на втором"
SIZE_AFTER = re.compile(r"\s+на\s+\d")
SIZE_BEFORE = re.compile(r"(?<![\d:.,])\d+\s+на\s+$")
GOES_ON = re.compile(r"[:.,]\d")       # ... and a number with one after it: "до 20:00" is a time, not a count
# two numbers of one noun: a range "2-3", a share "5/5" - both in the case of the word before the first and
# agreeing with the word after the second ("до двух-трёх человек", "с двумя-тремя магами"); not "20-00" (a time)
PAIR_NEXT = re.compile(r"\s*[-–/]\s*([1-9]\d*)\b")
PAIR_BEFORE = re.compile(r"(?<![\d:.,])\d+\s*[-–/]\s*$")
PREV_WORD = re.compile(r"(?<![\w'+-])([а-яёА-ЯЁ]+(?:-[а-яёА-ЯЁ]+)?)\s+$")   # a whole word, as morph.PREVIOUS
# the cases a preposition asks of the word after it (only those a count never takes in the singular);
# "нет" is no preposition but asks the genitive the same way ("нет 5 места", "нет 5 игроков") - or is an
# answer ("нет 2 хила уже есть"), see `asked_by`
GOVERNS = {**dict.fromkeys(("с", "со"), {"gent", "ablt"}),
           **dict.fromkeys(("до", "от", "из", "для", "без", "после", "около", "у", "кроме", "из-за", "из-под", "нет"), {"gent"}),
           **dict.fromkeys(("к", "ко", "по"), {"datv"}),
           **dict.fromkeys(("в", "во", "на", "о", "об", "при"), {"loct"}),
           **dict.fromkeys(("за", "под", "над", "перед"), {"ablt"})}
OBLIQUE = {"gent", "datv", "ablt", "loct"}
# a mass measured out, not counted: its singular after a number is an amount in any case ("до 200 опыта",
# "без 50 маны", "без 10 силы", "до 20 ткани"), never an ordinal; pymorphy marks some of them Sgtm, not these:
# resources, money, a character's stats, materials
MEASURED = {"опыт", "урон", "здоровье", "мана", "энергия", "ярость", "репутация", "исцеление", "лечение",
            "золото", "золотой", "серебро", "медь", "голда",
            "сила", "ловкость", "выносливость", "интеллект", "дух", "защита", "броня", "бронь", "меткость",
            "точность", "сопротивление", "уклонение", "парирование", "скорость", "рейтинг", "крит",
            "ткань", "кожа", "руда", "трава", "шерсть", "шёлк", "железо", "торий", "олово", "бронза", "сталь"}
# a number this large before a noun in the genitive singular that does not number (NUMBERED) is an amount ("до
# 225 навыка", "от 300 защиты"), not a place in a row - except a year ("до 2020 года"); in another case it is
# a place: "100 место", "на 120 странице", "1000 игрок" - "тысячный". Over a thousand it is an amount in any
# case (the dictionary's "10к" is "10000": "10к репа" - "десять тысяч", not "десятитысячная")
AMOUNT_FROM = 100
AMOUNT_OVER = 1000
YEAR = "год"
# a time of day: "до 5 утра", "с 8 вечера" - the hour counted, not "до пятого утра"
DAYTIME = {"утро", "день", "вечер", "ночь"}   # "до 2 дня" - "до двух дня" (an event's day would be "второго")
AT_HOUR = {"до", "с", "со", "после", "около", "от", "к", "ко", "в", "во", "на"}   # "для 2 дня" is the second day


def asked_by(before: str, n: int, word: str, morph) -> set[str]:
    """The cases `before`, the word before the number `n`, asks of `word` after it (GOVERNS). "нет" asks
    the genitive only where the line has no other reading: before a noun in the genitive plural ("нет 2
    хилов", "нет 5 игроков") or in the singular after 1 or 5+ ("нет 5 места"); "нет 2 хила уже есть" and
    "нет 5" alone are an answer and a count."""
    cases = GOVERNS.get(before.lower(), set())
    if before.lower() != "нет":
        return cases
    if not word:
        return set()
    few = 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14
    if few and not any(p.tag.POS == "NOUN" and p.tag.case == "gent" and p.tag.number == "plur"
                       for p in morph.parse(word.replace("+", "").lower())):
        return set()
    return cases
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
    abbreviation "СТО", which it lists first). "тысяча", "миллион" are nouns: plural after any
    number but one ("две тысячи" - "двух тысяч", "одна тысяча" - "одной тысячи")."""
    out = []
    for i, w in enumerate(words):
        parses = morph.parse(w)
        parse = next((p for p in parses if p.tag.POS == "NUMR"), parses[0])
        grammemes = {case}
        if parse.normal_form in ("тысяча", "миллион", "миллиард"):
            grammemes.add("sing" if i and words[i - 1] in ("один", "одна") else "plur")
        form = parse.inflect(grammemes)
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
    asked = asked_by(before, n, word, morph)
    parts = spoken.split()
    one = n % 10 == 1 and not 10 < n % 100 < 20
    if "gent" in asked and word in ("до", "по"):
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


# where a count of one is in the accusative: "через одну-две минуты", "на один-два часа"
ACCUSATIVE = {"в", "во", "на", "за", "через", "про"}


def first_of_pair(n: int, last: int, spoken: str, following: str, morph, before: str = "") -> str:
    """`spoken` (num2words' nominative for `n`), the first of two numbers of one noun, `last` the second:
    in the case the second takes ("до двух-трёх человек", "с двумя-тремя магами"). One ending in 1 does
    not take the noun's case, which is the form the second number asks ("места" after "два" is a
    genitive): it takes the case the preposition asks - the noun only choosing among the cases one may
    ask ("с одним-двумя магами") - and the noun's gender: "осталось одно-два места", "через одну-две
    минуты", "до одного-двух мест", "21-22 уровня" - "двадцать один-двадцать два"."""
    if n % 10 != 1 or n % 100 == 11:
        return agree(n, spoken, following, morph, before)
    word = following.replace("+", "").lower()
    nouns = [p for p in morph.parse(word) if p.tag.POS == "NOUN"] if morph.word_is_known(word) else []
    asked = asked_by(before, last, word, morph)
    case = next((c for c in CASES if c in asked and any(p.tag.case == c for p in nouns)), None)
    if case is None and asked in ({"gent"}, {"datv"}):
        case = next(iter(asked))                       # "до 1-2 человек", "по одному-два человека"
    if case is None:
        case = "accs" if before.lower() in ACCUSATIVE else "nomn"
    gender = next((p.tag.gender for p in nouns if p.tag.gender in GENDERS), "masc")
    one = morph.parse("один")[0].inflect({case, gender} | ({"inan"} if case == "accs" and gender == "masc" else set()))
    parts = spoken.split()
    if one:
        parts[-1] = one.word
    if case in OBLIQUE:
        parts[:-1] = to_case(parts[:-1], case, morph)  # "у двадцати одного-двадцати двух игроков"
    return " ".join(parts)


def ordinal(n: int, before: str, following: str, morph) -> str | None:
    """`n` as an ordinal agreeing with the word after it, when only an ordinal fits the phrase:
    "с 15 уровня" -> "пятнадцатого", "на 2 этаже" -> "втором", "15 уровень" -> "пятнадцатый"
    (a count wants a plural there: "15 уровней"); in the case a preposition asks, a count of 2 or
    more takes the plural, so a singular there is an ordinal even when the word has a plural of the
    same spelling ("до 15 места", "с 2 места"; "2 места в рейд" is a count). None when a count may
    be meant ("200 опыта" - "сколько", "до 200 опыта" - a mass, "за 2 часа", "5 раз", slang
    pymorphy does not know).
    A word that numbers rather than counts (NUMBERED) settles what the grammar leaves open: after
    a number ending in 1 ("с 21 уровня" - "двадцать первого", where "по 1 золотому" stays "одному")
    and in the genitive without a preposition ("хил 15 уровня", where "200 опыта" stays "двести")."""
    from num2words import num2words
    word = following.replace("+", "").lower()
    if not morph.word_is_known(word):
        return None
    parses = [p for p in morph.parse(word) if p.tag.POS == "NOUN"]
    if any(p.normal_form in MEASURED or "Sgtm" in p.tag for p in parses):
        return None                                    # "до 200 опыта", "из 100 золота": an amount
    if n >= AMOUNT_FROM and (n > AMOUNT_OVER or any(p.tag.case == "gent" and p.tag.number == "sing" for p in parses)) \
            and not any(p.normal_form in NUMBERED or p.normal_form == YEAR for p in parses):
        return None                                    # "до 225 навыка", "10000 репа"
    if before.lower() in AT_HOUR and any(p.normal_form in DAYTIME and p.tag.case == "gent" for p in parses):
        return None                                    # "до 3 ночи": an hour
    numbered = any(p.normal_form in NUMBERED for p in parses)
    asked = asked_by(before, n, word, morph)
    governed = [p for p in parses if p.tag.case in asked]
    if numbered:
        parses = [p for p in parses if p.tag.number == "sing"]   # "с 3 фазы", not "3 фазы" (plural)
    elif governed:                                     # "до 15 места": not the plural "места" (nominative)
        if any(p.tag.number != "sing" for p in governed):
            return None                                # "до 2 часов": a count in the genitive
        parses = governed
    elif any(p.tag.number != "sing" for p in parses):
        return None
    if not parses:
        return None
    if n % 10 == 1 and n % 100 != 11 and not numbered:
        return None                                    # "по 1 золотому", "без 1 руки": a count reads so too
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
# which is not a noun the number counts or numbers ("пятидесятый плюс"): a cardinal, in the preposition's case;
# so is the dictionary's "икс" ("х2" - "икс два": "уровень 40 икс два")
SIGNS = {"плюс", "минус", "икс"}
# an ordinal's ending glued to its number: "40го", "2007-го", "на 4м этаже" - the ordinal in that form
# ("2х2" is no "двух": a digit after the ending)
ENDING = re.compile(r"-?(ого|его|ому|ему|ыми|ими|ым|им|ом|ем|ый|ий|ой|ая|яя|ое|ее|ую|юю|ых|их|ые|ие|ух|ех|го|му|м|й|я|е|ю|х)"
                    r"(?![а-яёa-z\d])", re.IGNORECASE)
LETTERS_AFTER = re.compile(r"[а-яёa-z]+", re.IGNORECASE)   # "200ХП", "5м": letters glued to a number, read apart
# a cardinal's case ending glued to it: "до 5ти человек" - "пяти", "с 3мя" - "тремя"
CARDINAL_ENDING = re.compile(r"-?([а-яё]{2,3})(?![а-яёa-z\d])", re.IGNORECASE)
CASES = ("gent", "datv", "ablt", "loct")
# a number and "-ка": a noun of its own ("ходим в 40ку" - "в сороковку", "10ка" - "десятка")
NOUN_OF = {5: "пятёрк", 10: "десятк", 20: "двадцатк", 40: "сороковк", 100: "сотк"}
NOUN_ENDING = re.compile(r"-?к(а|у|е|и|ой|ами|ах|ам)(?![а-яёa-z\d])", re.IGNORECASE)
# "идём в 4м" (and no noun after it): together, so many of us - not "в четвёртом"; "стоим в 5 м" is metres
TOGETHER = re.compile(r"\b([вВ])\s*([2-9]|10)-?м\b(?!\s*[а-яёa-z])")
COLLECTIVE = {2: "двоём", 3: "троём", 4: "четвером", 5: "пятером", 6: "шестером", 7: "семером", 8: "восьмером",
              9: "девятером", 10: "десятером"}
SAME_CASE = {"loc2": "loct", "gen2": "gent", "acc2": "accs"}


def ending_form(n: int, ending: str, before: str, morph, noun: str = "") -> str | None:
    """`n` as the ordinal whose form ends in `ending` ("40го" - "сорокового"), agreeing with the noun
    after it ("на 10й минуте" - "десятой", "по 5-й уровень" - "пятый"), the case the preposition before it
    asks for preferred ("на 4м этаже" - "четвёртом"). A lone "м" only with such a noun: "до 5м", "за 5м до
    рейда" are minutes or metres. None when none ends so."""
    from num2words import num2words
    parts = num2words(n, lang="ru", to="ordinal").split()
    asked = GOVERNS.get(before.lower(), set()) | ({"accs"} if before.lower() in ("в", "во", "на", "за", "про", "по") else set())
    forms = [f for f in morph.parse(parts[-1])[0].lexeme if f.word.endswith(ending.lower())]
    word = noun.replace("+", "").lower()
    parses = morph.parse(word) if word and morph.word_is_known(word) else []
    nouns = [p.tag for p in parses if p.tag.POS == "NOUN"] if parses and parses[0].tag.POS == "NOUN" else []

    def agrees(form, tag) -> bool:
        if form.tag.case != SAME_CASE.get(tag.case, tag.case) or form.tag.number != tag.number:
            return False
        return tag.number == "plur" or form.tag.gender == tag.gender

    agreeing = [f for f in forms if any(agrees(f, t) for t in nouns)]
    if agreeing:
        forms = agreeing
    elif ending.lower() == "м":
        return None
    if not forms:
        return None
    best = next((f for f in forms if f.tag.case in asked), forms[0])
    parts[-1] = best.word
    return " ".join(parts)


def glued_word(n: int, spoken: str, letters: str, morph) -> str | None:
    """`n` with letters glued to it that make a form of the number itself: a cardinal's case ending
    ("5ти" - "пяти", "7ми" - "семи"), or "-ка" of a noun ("40ку" - "сороковку")."""
    noun = NOUN_ENDING.fullmatch(letters)
    if noun and n in NOUN_OF:
        return NOUN_OF[n] + noun.group(1).lower()
    ending = letters.lstrip("-").lower().replace("ё", "е")
    for case in CASES:
        words = to_case(spoken.split(), case, morph)
        if words[-1].replace("ё", "е").endswith(ending):
            return " ".join(words)
    return None


# a preposition said in its long form before the number's word: "со второго", "со ста", "во втором",
# "ко второму", "об одном"
LONG_PREPOSITION = re.compile(r"(?<![\w'+-])([сСвВкКоО])(\s+)$")
LONG_BEFORE = {"с": re.compile(r"[вфсзшжщ][^аеёиоуыэюя]"), "в": re.compile(r"[вф][^аеёиоуыэюя]"),
               "к": re.compile(r"в[^аеёиоуыэюя]"), "о": re.compile(r"[аеиоуыэ]")}
LONG_FORM = {"с": "о", "в": "о", "к": "о", "о": "б"}


def long_preposition(before: str, spoken: str) -> str:
    """`before` (the text up to a number) with its last word, a one-letter preposition, in the form
    the number's word asks: "с 2 места" - "со второго места", "о 11 боссах" - "об одиннадцати"."""
    m = LONG_PREPOSITION.search(before)
    if not m:
        return before
    letter = m.group(1).lower()
    if not LONG_BEFORE[letter].match(spoken.lower()):
        return before
    return before[:m.start()] + m.group(1) + LONG_FORM[letter] + m.group(2)


# a range "с N по M": both are ordinals of the noun after M ("с 1 по 5 уровень" - "с первого по пятый",
# "с 1 по 3 босса" - "с первого по третьего босса"); the dictionary may have made M's ordinal already
# ("по двадцать пятый уровень": the noun's ordinal is its last word)
RANGE_START = re.compile(r"\s+по\s+(?:\d+(?:-?[а-яё]{1,3})?\s+)?((?:[а-яёА-ЯЁ+]+(?:-[а-яёА-ЯЁ+]+)*\s+){0,3}[а-яёА-ЯЁ+]+(?:-[а-яёА-ЯЁ+]+)*)")
RANGE_END = re.compile(r"(?<![\w'+-])(?:с|со)\s+\d+(?:-?[а-яё]{1,3})?\s+по\s+$", re.IGNORECASE)
# a date: the day is a neuter ordinal ("пятое мая"), in the genitive without a preposition ("рейд пятого
# мая") or after one that asks it ("до пятого мая"), else in the preposition's case ("к пятому мая", "по пятое")
MONTHS = {"января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября",
          "ноября", "декабря"}
DATE_CASES = {**dict.fromkeys(("к", "ко"), "datv"), **dict.fromkeys(("по", "на", "в", "во", "за", "про", "через"), "accs"),
              **dict.fromkeys(("о", "об", "при"), "loct"), **dict.fromkeys(("перед", "под", "над", "между"), "ablt")}
# what is never the noun a range numbers: a function word, a name
NOT_NUMBERED = ("PREP", "CONJ", "PRCL", "INTJ", "Name", "Surn", "Patr", "Geox", "Orgn", "Abbr")


def closing_word(words: str, morph) -> str:
    """The word that stands for the noun closing a range, from the words after "по M": the first one
    that is not a cardinal ("двадцать пятый уровень" - "пятый")."""
    split = words.split()
    for word in split:
        if not any(p.tag.POS == "NUMR" for p in morph.parse(word.replace("+", "").lower())):
            return word
    return split[-1]


def range_tag(word: str, morph) -> tuple[str, str | None] | None:
    """The gender and animacy for the ordinals of a range closed by `word`: a singular noun in the
    case "по" gives it there - the accusative (or the nominative it shares), never the dative of "по 5
    золотых" - or an ordinal standing for it ("по пятый уровень"), or a month ("с 1 по 5 января" - the
    days, neuter). The animacy only when the noun is typed in the accusative: "по 3 босса" - "третьего",
    "по 4 босс" - "четвёртый", as typed. None for anything else - pymorphy's best reading a function word
    or a name ("с 1 по 5 и дальше", "по Москве"), no such form: a count."""
    word = word.replace("+", "").lower()
    if word in MONTHS:
        return "neut", None
    if word in SIGNS or not morph.word_is_known(word):
        return None
    parses = morph.parse(word)
    top = parses[0]
    if any(g in top.tag for g in NOT_NUMBERED):
        return None
    if top.tag.POS == "ADJF" and "Anum" in top.tag:
        forms = [p for p in parses if p.tag.POS == "ADJF" and "Anum" in p.tag and p.tag.number == "sing"
                 and p.tag.case in ("accs", "nomn")]
        return (forms[0].tag.gender or "masc", None) if forms else None
    if top.tag.POS != "NOUN":
        return None
    forms = sorted((p for p in parses if p.tag.POS == "NOUN" and p.normal_form == top.normal_form
                    and p.tag.number == "sing" and p.tag.case in ("accs", "nomn")), key=lambda p: p.tag.case != "accs")
    if not forms:
        return None
    tag = forms[0].tag
    return tag.gender or "masc", tag.animacy if tag.case == "accs" else None


def ordinal_as(n: int, gender: str, animacy: str | None, case: str, morph) -> str | None:
    """`n` as an ordinal in `case` and `gender` (and `animacy`, in the accusative of the masculine)."""
    from num2words import num2words
    grammemes = {case, gender, "sing"}
    if case == "accs" and animacy and gender == "masc":
        grammemes.add(animacy)                         # "по третьего босса", "по пятый уровень"
    parts = num2words(n, lang="ru", to="ordinal").split()
    form = morph.parse(parts[-1])[0].inflect(grammemes)
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
    morph = analyzer()
    text = TOGETHER.sub(lambda m: m.group(1) + COLLECTIVE[int(m.group(2))], text)

    def spell(m) -> tuple[str, int]:
        """The number in words, and where the text it stands for ends (past the word after it
        when that word's stress is settled here too)."""
        if len(m.group()) >= 10:
            return m.group(), m.end()
        n = int(m.group())
        spoken = num2words(n, lang="ru")
        pair = PAIR_BEFORE.search(m.string, 0, m.start()) if not m.group().startswith("0") else None
        before = PREV_WORD.search(m.string, 0, pair.start() if pair else m.start())   # "до 2-3": "до" for both
        before = before.group(1) if before else ""
        glued = ENDING.match(m.string, m.end())
        if glued and morph is not None:
            ending = glued.group(1).lower()
            if ending in ("х", "ух", "ех"):              # "из 2х", "3х": a count in the genitive - "двух", "трёх"
                return " ".join(to_case(spoken.split(), "gent", morph)), glued.end()
            # a lone "м" is an ordinal only after a preposition ("на 4м этаже"); "через 5м" is minutes or metres
            if ending != "м" or before.lower() in GOVERNS:
                noun = NEXT_WORD.match(m.string, glued.end())
                as_ordinal = ending_form(n, glued.group(1), before, morph,
                                         noun.group(1).rsplit("-", 1)[-1] if noun else "")
                if as_ordinal:
                    return as_ordinal, glued.end()
        if SIZE_AFTER.match(m.string, m.end()) or SIZE_BEFORE.search(m.string, 0, m.start()):
            return spoken, m.end()                     # "2 на 2 арена" - "два на два"
        own = (NOUN_ENDING.match(m.string, m.end()) or CARDINAL_ENDING.match(m.string, m.end())) if morph else None
        if own and (word := glued_word(n, spoken, own.group(), morph)):
            return word, own.end()                     # "до 5ти" - "до пяти", "в 40ку" - "в сороковку"
        if LETTERS_AFTER.match(m.string, m.end()):
            if morph is not None and asked_by(before, n, "", morph) == {"gent"}:
                spoken = " ".join(to_case(spoken.split(), "gent", morph))
            return spoken + " ", m.end()                # "200ХП" - "двести ХП", "до 5м" - "до пяти м"
        following = NEXT_WORD.match(m.string, m.end())
        if GLUED.search(m.string, 0, m.start()):
            following = None                           # "20:00 сбор", "1.12 патч": no "нулевой сбор"
        if morph is not None and following and before.lower() in ("с", "со") and following.group(1).lower() == "по":
            closing = RANGE_START.match(m.string, m.end())
            tag = range_tag(closing_word(closing.group(1), morph), morph) if closing else None
            as_ordinal = ordinal_as(n, *tag, "gent", morph) if tag else None
            if as_ordinal:
                return as_ordinal, m.end()             # "с первого по пятый уровень"
        if morph is not None and following and before.lower() == "по" and RANGE_END.search(m.string, 0, m.start()):
            tag = range_tag(following.group(1), morph)
            as_ordinal = ordinal_as(n, *tag, "accs", morph) if tag else None
            if as_ordinal:
                return as_ordinal, m.end()             # "по третьего босса", "по пятое января"
        if morph is not None and following and following.group(1).lower() in MONTHS and 1 <= n <= 31:
            date = ordinal_as(n, "neut", None, DATE_CASES.get(before.lower(), "gent"), morph)
            if date:
                return date, m.end()                   # "до пятого мая"
        if morph is not None and following and following.group(1).lower() in SIGNS:
            # "от 50+" - "от пятидесяти плюс"; "на 3+ человек" stays "на три плюс" (the accusative)
            case = "gent" if "gent" in asked_by(before, n, "", morph) else None
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
        elif morph is not None and (second := PAIR_NEXT.match(m.string, m.end())) and \
                (noun := NEXT_WORD.match(m.string, second.end())):
            try:                                       # the first of two: "до 2-3 человек" - "до двух-"
                spoken = first_of_pair(n, int(second.group(1)), spoken, noun.group(1).rsplit("-", 1)[-1], morph, before)
            except Exception:  # noqa: BLE001 - a number read in the nominative is still a number
                pass
        elif morph is not None and not GOES_ON.match(m.string, m.end()) and \
                (case := "gent" if asked_by(before, n, "", morph) == {"gent"} else "datv" if before.lower() in ("к", "ко") else None):
            spoken = " ".join(to_case(spoken.split(), case, morph))     # "ждём до 10." - "до десяти", "2 к 1" - "к одному"
        return spoken, m.end()

    out, pos = [], 0
    for m in NUMBER.finditer(text):
        if m.start() < pos:
            continue                                   # inside a word taken with the number before
        spoken, end = spell(m)
        out += [long_preposition(text[pos:m.start()], spoken), spoken]
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
