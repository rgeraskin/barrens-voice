"""Declension of dictionary replacements after prepositions (needs pymorphy3)."""
import importlib.util
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bv.morph import Inflector, strip_marks  # noqa: E402

HAVE = importlib.util.find_spec("pymorphy3") is not None


def m(s):
    return "\x02" + s + "\x03"


class Marks(unittest.TestCase):
    def test_without_pymorphy_marks_go(self):
        self.assertEqual(Inflector(print, enabled=False).apply("в " + m("Огненная пропасть")), "в Огненная пропасть")
        self.assertEqual(strip_marks(m("a") + m("b")), "ab")


@unittest.skipUnless(HAVE, "pymorphy3 not installed")
class Declension(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inf = Inflector(print)

    def check(self, text, expected):
        self.assertEqual(self.inf.apply(text), expected)

    def test_cases(self):
        self.check("идём в " + m("Огненная пропасть"), "идём в Огненную пропасть")
        self.check("из " + m("Огненная пропасть"), "из Огненной пропасти")
        self.check("для " + m("Мёртвые копи"), "для Мёртвых копей")
        self.check("в " + m("Мёртвые копи"), "в Мёртвые копи")
        self.check("к " + m("Тюрьма Штормграда"), "к Тюрьме Штормграда")
        self.check("на " + m("Нижняя часть Пика Чёрной горы"), "на Нижнюю часть Пика Чёрной горы")
        self.check("с " + m("дальний дам+агер"), "с дальним дам+агером")

    def test_names_and_conjunctions(self):
        self.check("для " + m("Зул'Ф+аррак"), "для Зул'Ф+аррака")
        self.check("в " + m("Ульдам+ан"), "в Ульдам+ан")
        self.check("с " + m("т+анк") + " и " + m("чернокнижник"), "с т+анком и чернокнижником")
        self.check("нужен " + m("т+анк") + " и " + m("х+ил"), "нужен т+анк и х+ил")
        self.check(m("продам") + " сумки", "продам сумки")

    def test_things_and_hyphens(self):
        # pymorphy reads nominative "руины" only as animate: the thing reading declines right
        self.check("в " + m("ру+ины Лордер+она"), "в ру+ины Лордер+она")
        self.check("из " + m("ру+ины Лордер+она"), "из ру+ин Лордер+она")
        # a hyphenated word declines as one: "рейд-лидером", not "рейдом лидер"
        self.check("с " + m("рейд-лидер"), "с рейд-лидером")
        self.check("для " + m("рейд-лидер"), "для рейд-лидера")

    def test_whole_word_before(self):
        # a unit glued to a number is no preposition: "10к хп", "5с кд"
        self.check("у босса 10к " + m("здоровье"), "у босса 10к здоровье")
        self.check("5с " + m("кулд+аун"), "5с кулд+аун")
        self.check("2к " + m("г+олды"), "2к г+олды")
        # a hyphenated preposition is one word
        self.check("из-за " + m("Огненная пропасть"), "из-за Огненной пропасти")
        self.check("из-под " + m("поле боя"), "из-под поля боя")
        self.check("кто-то в " + m("Огненная пропасть"), "кто-то в Огненную пропасть")


if __name__ == "__main__":
    unittest.main()
