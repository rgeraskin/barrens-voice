"""Declension of the dictionary's replacements after a preposition ("в ОП" -> "в Огненную
пропасть", "для дд" -> "для дамагера"), with pymorphy3.

The dictionary (`Dictionary.apply_words`, and `Dictionary.apply` for its regexes) marks each
replacement as \\x02...\\x03. The case comes from the word before it; only the start of the
replacement is declined - adjectives and the first noun - so a name's genitive tail stays
("Глубины Чёрной горы" -> "в Глубины Чёрной горы").
"""
from __future__ import annotations

import re
import threading

MARKED = re.compile(r"\x02([^\x02\x03]*)\x03")
# the whole word before a replacement: not the unit glued to a number ("10к хп", "5с кд": no "к", "с"),
# nor the end of a hyphenated one ("из-за")
PREVIOUS = re.compile(r"(?<![\w'+-])([а-яё]+(?:-[а-яё]+)?)\W*$", re.IGNORECASE)
WORD = re.compile(r"[\w'+]+(?:-[\w'+]+)*|[^\w'+]+")   # "рейд-лидер" is one word: its second half declines

# Preposition -> case. "в"/"на" can be "where" (prepositional) as well as "where to" (accusative);
# chat looking for groups means "where to" far more often.
CASES = {
    "в": "accs", "во": "accs", "на": "accs", "за": "accs", "через": "accs", "про": "accs",
    "из": "gent", "изо": "gent", "у": "gent", "до": "gent", "для": "gent", "после": "gent", "от": "gent",
    "без": "gent", "возле": "gent", "около": "gent", "кроме": "gent", "вместо": "gent", "из-за": "gent",
    "из-под": "gent",
    "к": "datv", "ко": "datv", "по": "datv",
    "с": "ablt", "со": "ablt", "под": "ablt", "над": "ablt", "перед": "ablt", "между": "ablt",
    "о": "loct", "об": "loct", "при": "loct",
}
DECLINABLE = {"ADJF", "PRTF", "NOUN"}
# names pymorphy knows: a word it knows only as one, written in small letters, is slang it took for a name
# («кача», as the town Кача: «для кача» became «для качи») - left as typed
PROPER = ("Geox", "Name", "Surn", "Patr", "Orgn", "Trad")
CONJUNCTIONS = {"и", "или", "либо", "да"}   # "с танком и чернокнижником": the case carries over
# "с 1 по ..." - a range: a number or an ordinal between "с" and "по" ("с первого по"; "с тобой по кд"
# is no range: "по кулдауну")
RANGE = re.compile(r"(?<![\w'+-])(?:с|со)\s+(\d+(?:-?[а-яё]{1,3})?|[а-яё]+)(?:\s+года)?\s+по\W*$", re.IGNORECASE)


KEEP = "\x06"   # first in a marked replacement: not declined - the dictionary's «=!» (dictionary.KEEP_CASE); not
                # \x04/\x05, the protocol's marks after a name (protocol.NAME_MARK): one sign, one meaning


def strip_marks(text: str) -> str:
    return text.replace("\x02", "").replace("\x03", "").replace(KEEP, "")


class Inflector:
    def __init__(self, log, enabled: bool = True):
        self.log, self.enabled, self.morph = log, enabled, None
        self.lock = threading.Lock()

    def load(self) -> None:
        if not self.enabled or self.morph is not None:
            return
        from .text import analyzer
        self.morph = analyzer()                      # the one the numbers use too
        if self.morph is None:
            self.log("pymorphy3 не установлен: замены словаря не склоняются")
            self.enabled = False

    def apply(self, text: str) -> str:
        """`text` with each marked replacement declined after its preposition, marks removed."""
        if "\x02" not in text:
            return text
        if not self.enabled:
            return strip_marks(text)
        with self.lock:
            self.load()
            if self.morph is None:
                return strip_marks(text)
            out, last, carried = [], 0, None
            for m in MARKED.finditer(text):
                before = text[last:m.start()]
                out.append(before)
                prev = PREVIOUS.search(strip_marks("".join(out)))
                word = prev.group(1).lower() if prev else ""
                if word == "по" and self._range(strip_marks("".join(out))):
                    case = "accs"           # "с 1 по <5> уровень": up to, not the dative of "по 5 золотых"
                elif word in ("с", "со") and self._ordinal_first(m.group(1)):
                    case = "gent"           # "с <60> лвл": from level sixty, not "with the sixtieth level"
                elif word in CASES:
                    case = CASES[word]
                elif word in CONJUNCTIONS and re.fullmatch(r"\s*\w+\s*", before):
                    case = carried          # "X и Y": Y takes X's case
                else:
                    case = None
                keep = m.group(1).startswith(KEEP)        # «=!» in the dictionary: as written, whatever comes before
                out.append(self.decline(m.group(1), case) if case and not keep else m.group(1))
                carried = case
                last = m.end()
            out.append(text[last:])
            return strip_marks("".join(out))

    def _range(self, text: str) -> bool:
        """Whether `text` ends in "с N по" (N a number or an ordinal word)."""
        m = RANGE.search(text)
        return bool(m) and (m.group(1)[0].isdigit() or any("Anum" in p.tag for p in self.morph.parse(m.group(1).lower())))

    def _ordinal_first(self, phrase: str) -> bool:
        """Whether `phrase` starts with an ordinal (a compound's cardinal words before it): "шестидесятый
        уровень", "пятьдесят пятый уровень" - a replacement of the dictionary's `<N>`."""
        for word in re.findall(r"[а-яё]+", phrase.replace("+", "").lower()):
            parses = self.morph.parse(word)
            if any("Anum" in p.tag for p in parses):
                return True
            if not any(p.tag.POS == "NUMR" for p in parses):
                return False
        return False

    def decline(self, phrase: str, case: str) -> str:
        """The start of `phrase` (adjectives up to and including the first noun) put in `case`."""
        parts = WORD.findall(phrase)
        words = [i for i, p in enumerate(parts) if re.match(r"[\w'+]", p)]
        parsed = {}
        head = None
        for n, i in enumerate(words):
            if self._cardinal(parts[i]) and self._ordinal_after(parts, words[n + 1:]):
                continue        # "пятьдесят пятый уровень": a compound ordinal declines its last word only
            p = self._parse(parts[i], adjective_first=n + 1 < len(words))
            if p is None or p.tag.POS not in DECLINABLE:
                break
            parsed[i] = p
            if p.tag.POS == "NOUN":
                head = p
                break
        if head is None:
            return phrase
        if case == "accs" and head.tag.gender in ("masc", "neut") and head.tag.number != "plur" and \
                not self.morph.word_is_known(parts[[i for i in parsed if parsed[i] is head][0]].replace("+", "").lower()):
            return phrase       # an unknown name (Ульдаман, Зул'Фаррак) is a place: accusative = nominative
        for i, p in parsed.items():
            grammemes = {case}
            if p.tag.POS != "NOUN":
                if head.tag.number:
                    grammemes.add(head.tag.number)
                if head.tag.number == "sing" and head.tag.gender:
                    grammemes.add(head.tag.gender)
                if case == "accs" and head.tag.animacy and (head.tag.number == "plur" or head.tag.gender == "masc"):
                    grammemes.add(head.tag.animacy)
            form = p.inflect(grammemes)
            if form is not None:
                parts[i] = self._like(parts[i], form.word)
        return "".join(parts)

    def _cardinal(self, word: str) -> bool:
        return any(p.tag.POS == "NUMR" for p in self.morph.parse(word.replace("+", "").lower()))

    def _ordinal_after(self, parts: list[str], rest: list[int]) -> bool:
        """Whether the words at `rest` begin with more cardinals and then an ordinal ("пятый")."""
        for i in rest:
            if not self._cardinal(parts[i]):
                return any("Anum" in p.tag for p in self.morph.parse(parts[i].replace("+", "").lower()))
        return False

    def _parse(self, word: str, adjective_first: bool = False):
        """The nominative reading of `word`; an adjective one first when a word follows ("Мёртвые
        копи": pymorphy's best guess for "мёртвые" is the noun "the dead")."""
        plain = word.replace("+", "")
        if not re.search(r"[а-яё]", plain, re.IGNORECASE):
            return None
        options = self.morph.parse(plain)
        if not options:
            return None
        if plain[:1].islower() and self.morph.word_is_known(plain.lower()) and \
                all(any(g in o.tag for g in PROPER) for o in options if o.tag.POS == "NOUN") and \
                any(o.tag.POS == "NOUN" for o in options):
            return None
        nominative = [o for o in options if o.tag.case == "nomn" and o.tag.POS in DECLINABLE]
        if adjective_first:
            adjectives = [o for o in nominative if o.tag.POS in ("ADJF", "PRTF")]
            if adjectives:
                return adjectives[0]
        best = (nominative or options)[0]
        if best.tag.animacy == "anim":
            # "руины": pymorphy reads the nominative only as animate, so "в руины" became "в руин" (the
            # animate accusative); a thing of the same word, if pymorphy knows one, declines right
            things = [o for o in options if o.tag.animacy == "inan" and o.normal_form == best.normal_form
                      and o.tag.POS == best.tag.POS and o.tag.number == best.tag.number]
            if things:
                return things[0]
        return best

    @staticmethod
    def _like(original: str, new: str) -> str:
        """`new` with the letter case of `original` (letter by letter, so "Зул'Фаррак" keeps its
        second capital) and its stress mark, when the stressed vowel is in the unchanged part."""
        plain = original.replace("+", "")
        new = "".join(c.upper() if i < len(plain) and plain[i].isupper() else c for i, c in enumerate(new))
        if "+" in original:
            at = original.index("+")
            common = 0
            while common < min(len(plain), len(new)) and plain[common].lower() == new[common].lower():
                common += 1
            if at < common:
                new = new[:at] + "+" + new[at:]
        return new
