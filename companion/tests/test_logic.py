"""Text, voice assignment and payload parsing (no Windows, no GPU)."""
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bv.assign import Assigner  # noqa: E402
from bv.dictionary import parse as parse_rules, unescape  # noqa: E402
from bv.gamevoices import Slot  # noqa: E402
from bv.protocol import parse  # noqa: E402
from bv.speech import sapi_rate  # noqa: E402
from bv.text import apply_stress, merge_marks  # noqa: E402


class Text(unittest.TestCase):
    def test_quest_number_dropped(self):
        from bv.text import plain
        self.assertEqual(plain("LFM [[25] Свиток с рунами (3513)]"), "LFM Свиток с рунами")
        self.assertEqual(plain("[Свиток (3513)] и (через 5 мин)"), "Свиток и (через 5 мин)")

    def test_dictionary_marks_win(self):
        original = "Нужен дам+агер в Мёртвые копи"
        accented = "Н+ужен дамаг+ер в М+ёртвые к+опи"   # RUAccent's guess for the slang word
        self.assertEqual(merge_marks(original, accented), "Н+ужен дам+агер в М+ёртвые к+опи")

    def test_misaligned_marks_what_matches(self):
        self.assertEqual(merge_marks("один два", "од+ин"), "од+ин два")       # unmatched words: as they were

    def test_stress_modes(self):
        self.assertEqual(apply_stress("дам+агер", "acute"), "дама́гер")
        self.assertEqual(apply_stress("дам+агер", "strip"), "дамагер")
        self.assertEqual(apply_stress("дам+агер", "plus"), "дам+агер")

    def test_sapi_rate(self):
        self.assertEqual(sapi_rate(0, 100), 0)
        self.assertEqual(sapi_rate(0, 300), 10)
        self.assertLess(sapi_rate(0, 50), 0)
        self.assertEqual(sapi_rate(5, 300), 10)


def slots():
    out = []
    for base in ("orc-male", "orc-male#60"):
        for shift in (0.0, -1.5, 1.5):
            sid = base if shift == 0 else f"{base}^{shift:+g}"
            out.append(Slot(sid, base, "orc", "male", shift, f"{sid}.wav", "текст"))
    out.append(Slot("human-female", "human-female", "human", "female", 0.0, "hf.wav", "текст"))
    out.append(Slot("human-male", "human-male", "human", "male", 0.0, "hm.wav", "текст"))
    out.append(Slot("creature/saurfang", "creature/saurfang", "", "", 0.0, "s.wav", "текст"))
    return out


class Assign(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "a.json"

    def tearDown(self):
        self.dir.cleanup()

    def test_orcs_differ_and_base_voices_first(self):
        a = Assigner(slots(), self.path)
        got = [a.slot_for(f"Орк{i}", "Orc", "2", now=1000 + i).id for i in range(6)]
        self.assertEqual(len(set(got)), 6, got)
        self.assertEqual({g for g in got[:2]}, {"orc-male", "orc-male#60"})

    def test_skyborne_own_voice_or_human(self):
        sky = Slot("skyborne-female", "skyborne-female", "skyborne", "female", 0.0, "sf.wav", "текст")
        a = Assigner(slots() + [sky], self.path)
        self.assertEqual(a.slot_for("Еноты Дикие", "Skyborne", "3", now=1).id, "skyborne-female")
        b = Assigner(slots(), Path(self.dir.name) / "b.json")         # no Russian Skyborne lines in the client
        self.assertEqual(b.slot_for("Еноты Дикие", "Skyborne", "3", now=1).id, "human-female")

    def test_retail_race_own_voice_or_kin(self):
        own = [Slot("goblin-female", "goblin-female", "goblin", "female", 0.0, "g.wav", "текст"),
               Slot("haranir-male", "haranir-male", "haranir", "male", 0.0, "h.wav", "текст"),
               Slot("orc-female", "orc-female", "orc", "female", 0.0, "o.wav", "текст")]
        a = Assigner(slots() + own, self.path)
        self.assertEqual(a.slot_for("Гоблинша", "Goblin", "3", now=1).id, "goblin-female")
        self.assertEqual(a.slot_for("Корень", "Harronir", "2", now=1).id, "haranir-male")   # the game's name
        self.assertEqual(a.slot_for("Маг", "MagharOrc", "3", now=1).id, "orc-female")       # no own voice: kin
        self.assertEqual(a.slot_for("Эльфийка", "VoidElf", "3", now=1).id, "human-female")  # nor kin's: human

    def test_stable_and_persisted(self):
        a = Assigner(slots(), self.path)
        first = a.slot_for("Громмаш-Степи", "Orc", "2", now=1).id
        self.assertEqual(a.slot_for("Громмаш-Степи", "Orc", "2", now=2).id, first)
        a.flush()                                                # as on exit
        b = Assigner(slots(), self.path)
        self.assertEqual(b.slot_for("Громмаш-Степи", "Orc", "2", now=3).id, first)

    def test_unknown_race_and_sex(self):
        a = Assigner(slots(), self.path)
        self.assertEqual(a.slot_for("Волчок", "Worgen", "3").id, "human-female")
        self.assertEqual(a.slot_for("Кто-то", "", "").race, "human")

    def test_override(self):
        a = Assigner(slots(), self.path, {"Тралл": "creature/saurfang"})
        self.assertEqual(a.slot_for("Тралл-Степи", "Orc", "2").id, "creature/saurfang")


class Regexes(unittest.TestCase):
    SAVED = r'WTS=продам\n~(\\d+)\\s*кк\\b=\\g<1>000000\n~(\\d+)\\s*к\\b=\\g<1>000\n~[=битая\n~(?=x)y=z'

    def test_saved_variables_round_trip(self):
        text = unescape(self.SAVED)
        self.assertIn("~(\\d+)\\s*к\\b=\\g<1>000", text)
        errors = []
        rules = parse_rules(text, errors.append)
        self.assertEqual(len(rules), 3)          # the broken one is reported and skipped
        self.assertEqual(len(errors), 1)
        out = "продам за 5к, а меч за 2 КК"
        for pattern, replacement in rules:
            out = pattern.sub(replacement, out)
        self.assertEqual(out, "продам за 5000, а меч за 2000000")

    def test_lookahead_split_at_last_equals(self):
        rules = parse_rules("~a(?=b)=c", print)
        self.assertEqual(rules[0][0].sub(rules[0][1], "ab"), "cb")

    def test_bad_replacement_skipped_at_load(self):
        # a group the pattern has not: said once when the dictionary loads, not on every chat line
        errors = []
        rules = parse_rules("~(\\d+)x=\\2 y\n~(\\d+)y=\\g<n>\n~(\\d+)z=\\1 з", errors.append)
        self.assertEqual([r for _, r in rules], ["\\1 з"])
        self.assertEqual(len(errors), 2)
        self.assertIn("замена", errors[0])


class Payload(unittest.TestCase):
    def test_options(self):
        line = parse("\x1f".join(["say", "Имя", "Orc", "2", "WARRIOR", "", "rate=120;voice=sapi", "a=b текст"]).encode())
        self.assertEqual((line.rate, line.voice, line.text), (120, "sapi", "a=b текст"))

    def test_text_with_equals_is_not_options(self):
        line = parse("\x1f".join(["say", "Имя", "Orc", "2", "WARRIOR", "", "x = 5"]).encode())
        self.assertEqual((line.rate, line.voice, line.text), (100, "", "x = 5"))

    def test_voice_names_with_spaces(self):
        name = "Microsoft Irina Desktop - Russian"
        line = parse("\x1f".join(["test", "Проверка", "", "", "", "", f"rate=100;voice=sapi;sapi={name}",
                                    "Привет!"]).encode())
        self.assertEqual((line.voice, line.sapi_voice, line.text), ("sapi", name, "Привет!"))

    def test_declension_option(self):
        on = parse("\x1f".join(["say", "И", "", "", "", "", "rate=100;voice=f5;decl=1", "т"]).encode())
        off = parse("\x1f".join(["say", "И", "", "", "", "", "rate=100;voice=f5;decl=0", "т"]).encode())
        bare = parse("\x1f".join(["say", "И", "", "", "", "", "rate=100;voice=f5", "т"]).encode())
        self.assertEqual((on.declension, off.declension, bare.declension), (True, False, True))

    def test_without_options(self):
        line = parse("\x1f".join(["say", "Имя", "Orc", "2", "WARRIOR", "", "150 золота"]).encode())
        self.assertEqual((line.rate, line.text), (100, "150 золота"))


class VoiceListFile(unittest.TestCase):
    def test_render(self):
        from bv.voicelist import label, render

        class V:
            def __init__(self, d, e, g):
                self.description, self.engine, self.gender = d, e, g
        voices = [V("Microsoft Svetlana Online (Natural) - Russian (Russia)", "edge", "Female"),
                  V("Aidar (Russian)", "silero", "Male"), V("Anna", "rhvoice", "Female"),
                  V('Microsoft Irina Desktop - Russian', "other", "Female")]
        self.assertEqual([label(v) for v in voices],
                         ["Svetlana (Edge)", "Aidar (Silero)", "Anna (RHVoice)", "Irina Desktop (Windows)"])
        text = render(voices, lambda v: "Irina" in v.description)
        self.assertIn('{ name = "Anna", label = "Anna (RHVoice)", gender = "Female", on = true },', text)
        self.assertIn('label = "Irina Desktop (Windows)", gender = "Female", on = false', text)


class Plurals(unittest.TestCase):
    def test_russian_forms(self):
        from bv.dictionary import plurals
        forms = "[дамагер|дамагера|дамагеров]"
        got = {n: plurals(f"{n} {forms}") for n in (0, 1, 2, 4, 5, 11, 12, 14, 21, 22, 25, 101, 111)}
        self.assertEqual(got[1], "1 дамагер")
        self.assertEqual(got[21], "21 дамагер")
        self.assertEqual(got[101], "101 дамагер")
        self.assertEqual(got[2], "2 дамагера")
        self.assertEqual(got[22], "22 дамагера")
        for n in (0, 5, 11, 12, 14, 25, 111):
            self.assertEqual(got[n], f"{n} дамагеров")
        self.assertEqual(plurals("текст [a|b] без числа"), "текст [a|b] без числа")


class StableVoices(unittest.TestCase):
    def test_switching_a_voice_off_moves_only_its_people(self):
        from bv.speech import Speaker, Voice
        sp = Speaker({"players": {}, "exclude": [], "gender_overrides": {}}, print)
        voices = [Voice(None, f"Voice{i}", "Male", "rhvoice") for i in range(12)]
        sp.all_voices = voices
        sp.set_disabled(set())
        names = [f"Игрок{i}" for i in range(200)]
        before = {n: sp.voice_for(n, "2").description for n in names}
        sp.set_disabled({"Voice3"})
        after = {n: sp.voice_for(n, "2").description for n in names}
        moved = [n for n in names if before[n] != after[n]]
        self.assertTrue(moved)
        self.assertTrue(all(before[n] == "Voice3" for n in moved), "only Voice3's people may move")
        self.assertGreater(len(set(before.values())), 8)      # still spread over the voices


class ResetAssignments(unittest.TestCase):
    def test_reset_forgets(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "a.json"
            a = Assigner(slots(), path)
            a.slot_for("Орк1", "Orc", "2", now=1)
            a.reset()
            self.assertEqual(Assigner(slots(), path).known, {})


class DictionaryInCompanion(unittest.TestCase):
    """The addon's dictionary applied by the program: the default from Dictionary.lua, the player's
    layer from the strip or the saved variables."""
    ADDON = Path(__file__).resolve().parents[2] / "addon" / "BarrensVoice"

    def book(self, addon=None):
        from bv.dictionary import Dictionary
        d = Dictionary({}, lambda *a: None, addon or self.ADDON)
        d.user_path = Path("/nonexistent")                 # no saved variables in the tests
        d.from_addon = "test"
        d.refresh()
        return d

    def test_rl(self):
        # «РЛ»: the Ruins of Lordaeron, unless the words around it say it is the raid leader
        from bv.morph import Inflector
        d, inf = self.book(), Inflector(print)

        def read(text):
            return inf.apply(d.apply(inf.apply(d.apply_words(text)), mark=True))
        self.assertEqual(read("встречаемся в РЛ"), "встречаемся в ру+ины Лордер+она")

    def test_percent_and_kach(self):
        from bv.morph import Inflector
        d, inf = self.book(), Inflector(print)

        def read(text):
            return inf.apply(d.apply(inf.apply(d.apply_words(text)), mark=True))
        self.assertEqual(read("здоровья 95%"), "здоровья 95 процентов")
        self.assertEqual(read("осталось 1%"), "осталось 1 процент")
        self.assertEqual(read("на 2 % больше"), "на 2 процента больше")
        self.assertEqual(read("кача нет"), "к+ача нет")
        self.assertEqual(read("из ЛИ лут"), "из Лабиринтов Иглошкурых л+ут")       # «ЛИ» in capitals only
        self.assertEqual(read("есть ли танк?"), "есть ли т+анк?")                     # the particle stays
        self.assertEqual(read("ну пздц"), "ну пиздец")
        self.assertEqual(read("у РЛ стоим"), "у ру+ин Лордер+она стоим")
        self.assertEqual(read("нужен РЛ на МК"), "нужен рейд-лидер на МК")
        self.assertEqual(read("РЛ сказал ждать"), "рейд-лидер сказал ждать")
        self.assertEqual(read("пишите РЛу"), "пишите рейд-лидеру")
        self.assertEqual(read("с рлом договорились"), "с рейд-лидером договорились")

    def test_default_entries(self):
        d = self.book()
        plain = lambda text: d.apply_words(text).replace("\x02", "").replace("\x03", "")
        self.assertEqual(plain("общаемся через Discord и в дискорде"), "общаемся через диск+орд и в диск+орде")
        # a stem keeps the ending typed in chat and is not marked for declension; a whole word is
        self.assertEqual(d.apply_words("встречаемся на перекрестке"), "встречаемся на перекр+ёстке")
        self.assertEqual(d.apply_words("идём в ОП"), "идём в \x02Огненная пр+опасть\x03")
        # the name typed in full: its stress (not the verb "пропасть"), and its case after a preposition
        self.assertEqual(d.apply_words("в Огненная Пропасть"), "в \x02Огненная пр+опасть\x03")
        self.assertEqual(d.apply_words("схожу в ПС"), "схожу в \x02Пещеры стенаний\x03")
        self.assertEqual(d.apply_words("продам поножи и поножей"), "продам п+оножи и п+оножей")
        self.assertEqual(d.apply_words("че там, в пве или пвп?"), "\x02чё\x03 там, в \x02пэ-вэ-й+е\x03 или \x02пэвэп+э\x03?")
        self.assertEqual(d.apply_words("серега, сереге"), "серёга, серёге")
        self.assertEqual(plain("на пикабу"), "на пикаб+у")
        self.assertEqual(plain("в 20 по мск"), "в 20 по эм-эс-к+а")
        self.assertEqual(plain("кто сдал кв? квас и квартира"), "кто сдал квест? квас и квартира")
        self.assertEqual(plain("пишите в тг"), "пишите в телегр+ам")
        self.assertEqual(plain("доведете до конца"), "довед+ёте до конца")
        self.assertEqual(plain("ага, пойдём"), "аг+а, пойдём")
        self.assertEqual(plain("сережа, у сережи, сережу"), "серёжа, у серёжи, серёжу")
        self.assertEqual(plain("пиши в лс"), "пиш+и в личку")
        self.assertEqual(plain("губа не дура"), "губ+а не дура")
        self.assertEqual(plain("хелло всем"), "хелл+оу всем")
        self.assertEqual(plain("с др тебя"), "с дэ-+эр тебя")
        self.assertEqual(plain("кто берет ружье"), "кто берёт ружьё")
        self.assertEqual(plain("нюдес, нюдесы и нюдсы"), "н+юдес, н+юдесы и н+юдсы")
        self.assertEqual(plain("чето не то"), "чёто не то")   # both readings are words; in WoW it is these
        self.assertEqual(plain("учусь манаменеджменту, менеджмент"), "учусь манам+енеджменту, м+енеджмент")
        self.assertEqual(plain("жду тикета, тикет закрыли"), "жду т+икета, т+икет закрыли")
        self.assertEqual(d.apply_words("чиловая игра, за чиловую"), "чил+овая игра, за чил+овую")
        self.assertEqual(d.apply_words("кто танчит? я танчу, вчера танчила"), "кто т+анчит? я т+анчу, вчера т+анчила")
        self.assertEqual(d.apply("за 5к"), "за 5000")                                           # a default regex
        from bv.dictionary import plurals
        self.assertEqual(plurals(d.apply("продам 6шт, 1 шт. и 2 шт")), "продам 6 штук, 1 штука и 2 штуки")

    def test_the_players_layer(self):
        d = self.book()
        d.from_addon = None
        d.receive({"id": "a1", "part": "2", "of": "2"}, "абв=где\n~го+=го\nмертвые копи=м+ёртвые к+опи")
        self.assertNotIn("абв", d.exact)                                      # part 1 still missing
        d.receive({"id": "a1", "part": "1", "of": "2"}, "!ОП=Огненная пропасть\nлок=варлок")
        self.assertEqual(d.apply_words("лок в оп"), "\x02варлок\x03 в оп")      # changed; deleted
        self.assertEqual(d.apply_words("абв"), "\x02где\x03")                   # added
        self.assertEqual(d.apply("гоооо"), "го")                                 # an own regex
        self.assertEqual(d.apply_words("идём в Мёртвые копи"), "идём в \x02м+ёртвые к+опи\x03")   # a phrase
        d.receive({"id": "b2", "part": "1", "of": "1"}, "-")                     # back to the default
        self.assertEqual(d.apply_words("лок"), "\x02чернокнижник\x03")

    def test_saved_variables_until_the_addon_sends(self):
        import tempfile
        from bv.dictionary import Dictionary
        with tempfile.TemporaryDirectory() as dd:
            path = Path(dd) / "BarrensVoice.lua"
            path.write_text('BarrensVoiceDB = {\n["dictionaryUser"] = "лок=лок\\n!ОП=Огненная пропасть",\n}\n',
                            encoding="utf-8")
            d = Dictionary({}, lambda *a: None, self.ADDON)
            d.user_path = path
            d.refresh()
            self.assertEqual(d.apply_words("лок в оп"), "\x02лок\x03 в оп")

    def test_a_changed_default_works_at_once(self):
        import os
        import shutil
        import tempfile
        with tempfile.TemporaryDirectory() as dd:
            addon = Path(dd) / "BarrensVoice"
            addon.mkdir()
            shutil.copy(self.ADDON / "Dictionary.lua", addon / "Dictionary.lua")
            d = self.book(addon)
            self.assertEqual(d.apply_words("ыыы"), "ыыы")
            lua = addon / "Dictionary.lua"
            lua.write_text(lua.read_text(encoding="utf-8").replace("D.DEFAULT = [[\n", "D.DEFAULT = [[\nыыы=смех\n", 1),
                           encoding="utf-8")
            os.utime(lua, (lua.stat().st_atime, lua.stat().st_mtime + 5))
            d.refresh()
            self.assertEqual(d.apply_words("ыыы"), "\x02смех\x03")

    def test_renamed_entries_of_the_addons_default(self):
        # the addon updated during play: the program takes its new default at once, while the player's layer is
        # still the old addon's (D.Migrate runs at the next /reload) - the old «к» rule deleted or changed there
        # brings none of the rules it became
        d = self.book()
        self.assertEqual(d.apply("за 5к и 2 к голды"), "за 5000 и 2000 г+олды")
        d.receive({"id": "old1", "part": "1", "of": "1"}, "!~(\\d+)\\s*к\\b=\\g<1>000")
        self.assertEqual(d.apply("за 5к и 2 к голды, продам за 3 к, за 5 к отдам"),
                         "за 5к и 2 к голды, продам за 3 к, за 5 к отдам")
        d.receive({"id": "old2", "part": "1", "of": "1"}, "~(\\d+)\\s*к\\b=\\g<1> тысяч")
        self.assertEqual(d.apply("за 5к и 2 к голды"), "за 5 тысяч и 2 тысяч голды")      # theirs alone

    def test_names_kept_out(self):
        from bv.protocol import split_name
        self.assertEqual(split_name("Лок пишет:\x04 привет"), ("Лок пишет:", " привет", True))
        self.assertEqual(split_name("Лок\x05 смеётся"), ("Лок", " смеётся", False))   # an emote keeps it
        self.assertEqual(split_name("привет"), ("", "привет", False))
        from bv.protocol import with_name
        from bv.text import plain
        name, rest, _ = split_name("Лок пишет:\x04 привет")
        self.assertEqual(with_name(name, plain(rest)), "Лок пишет: привет")      # plain strips the space
        name, rest, _ = split_name("Лок\x05 смеётся")
        self.assertEqual(with_name(name, plain(rest)), "Лок смеётся")            # not «Локсмеётся»
        self.assertEqual(with_name("", "привет"), "привет")                      # the name dropped


class Pipeline(unittest.TestCase):
    """A chat line's text through the real pipeline, in the program's order (`__main__.speech_text`,
    then the numbers as an engine says them), with the real default dictionary - the rules interact:
    a regex sees the words the dictionary replaced, the declension sees both."""
    ADDON = Path(__file__).resolve().parents[2] / "addon" / "BarrensVoice"

    @classmethod
    def setUpClass(cls):
        try:
            import num2words  # noqa: F401
            import pymorphy3  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("num2words / pymorphy3")
        from bv.dictionary import Dictionary
        from bv.morph import Inflector
        cls.book = Dictionary({}, lambda *a: None, cls.ADDON)
        cls.book.user_path = Path("/nonexistent")          # no saved variables in the tests
        cls.book.from_addon = "test"
        cls.book.refresh()
        cls.inflector = Inflector(lambda *a: None)

    def say(self, text, declension=True):
        from bv import yo
        from bv.__main__ import speech_text
        from bv.text import numbers_to_words
        return numbers_to_words(speech_text(text, self.book, self.inflector, declension, yo.restore))

    def check(self, cases, declension=True):
        for text, spoken in cases.items():
            self.assertEqual(self.say(text, declension), spoken, text)

    def test_lines(self):
        self.check({
            "нужен 1 танк и 2дд в ОП, 60 лвл": "нужен один т+анк и два дам+агера в Огненную пр+опасть, шестидесятый уровень",
            "до 60 лвл": "до шестидесятого уровня",
            # a two-word ordinal declines its last word
            "от 55 лвл": "от пятьдесят пятого уровня", "о 33 лвл": "о тридцать третьем уровне",
            "для 120 лвл": "для сто двадцатого уровня",
            "с БГ": "с полем боя",
            "продам меч за 5к": "продам меч за пять тысяч",
            "за 5з 20с": "за пять золотых двадцать серебра",
            "2г50с": "два золотых пятьдесят серебра", "за 5з20с": "за пять золотых двадцать серебра",
            "5g20s": "пять золотых двадцать серебра", "2г50": "два золотых пятьдесят", "5з20 каждый": "пять золотых двадцать каждый",
            "100г": "сто золотых", "продам за 50г": "продам за пятьдесят золотых", "за 1г": "за один золотой",
            # a year after «с», «в», «после»; a price stays gold
            "играю с 2005г": "играю с две тысячи пятого года", "гильдия с 2007г": "гильдия с две тысячи седьмого года",
            "в 2007г начал": "в две тысячи седьмом году начал", "после 2010г": "после две тысячи десятого года",
            "продам за 2000г": "продам за две тысячи золотых", "куплю до 2000г": "куплю до двух тысяч золотых",
            # a round hundred glued to «г» after «в» is a price («обошлось в 2000г»); spaced, or «году», it is a year
            "обошлось в 2000г": "обошлось в две тысячи золотых", "в 2000 г продал": "в двухтысячном году продал",
            "в 2000 году": "в двухтысячном году",
            "в 2010г": "в две тысячи десятом году",
            # «кк» after a number is millions, alone «окей» (it was a word, which went before the regexes)
            # a range of years: «по»/«до» right after a year (a price range stays gold)
            "играю с 2005г по 2010г": "играю с две тысячи пятого года по две тысячи десятый год",
            "с 2005 по 2010г": "с две тысячи пятого по две тысячи десятый год",
            "с 2005г до 2010г": "с две тысячи пятого года до две тысячи десятого года",
            "с 1000 по 2000г": "с одной тысячи по две тысячи золотых", "дам по 2000г": "дам по две тысячи золотых",
            "продам за 2 кк": "продам за два миллиона", "за 2кк": "за два миллиона", "кк, иду": "окей, иду",
            "через 30 сек пул": "через тридцать секунд п+ул",
            "скидка 50%": "скидка пятьдесят процентов",
        })

    def test_a_range_of_years_without_declension(self):
        # no declension marks around «года»: the rule's look back holds without them too
        self.assertIn("десятый год", self.say("играю с 2005г по 2010г", declension=False))

    def test_a_unit_glued_to_a_number_is_no_preposition(self):
        self.check({
            "5с кд": "пять секунд кулд+аун", "через 5с кд": "через пять секунд кулд+аун",
            "30с кд на сапе": "тридцать секунд кулд+аун на сапе", "2к голды": "две тысячи г+олды",
            "из-за ОП вайп": "из-за Огненной пр+опасти в+айп", "из-под БГ": "из-под поля боя",
        })

    def test_a_spaced_unit(self):
        # «к» with a space is thousands only before an amount or at the end; else a preposition. «5 с кд»
        # is seconds though «кд» has been declined after «с»
        self.check({
            "2 к голды": "две тысячи г+олды", "продам за 2 к": "продам за две тысячи", "3 к за ран": "три тысячи за ран",
            "5 к урона": "пять тысяч урона", "продам за 3 к, срочно": "продам за три тысячи, срочно",
            "плюс 5 к силе": "плюс пять к силе",
            "обмен 2 к 1": "обмен два к одному", "5 к ОП": "пять к Огненной пр+опасти",
            "5 с кд": "пять секунд кулд+аун", "2 с кд": "две секунды кулд+аун", "через 5 с кд": "через пять секунд кулд+аун",
            # a dative after «к» is the preposition's noun; an amount's other forms make thousands
            "5 к урону": "пять к урону", "2 к броне": "два к броне", "2 к золоту": "два к золоту",
            "5 к урон": "пять тысяч урон", "5 к мана": "пять тысяч мана",
            # after «плюс» (the addon's «+») «к» is a preposition whatever follows: a bonus
            "плюс 5 к урону": "плюс пять к урону", "чант плюс 7 к урону оружия": "чант плюс семь к урону оружия",
            "плюс 100 к здоровью": "плюс сто к здоровью", "плюс 70 к броне": "плюс семьдесят к броне",
            "плюс 15 к рейтингу": "плюс пятнадцать к рейтингу", "плюс 15 к урона": "плюс пятнадцать к урона",
            "плюс 10к хп": "плюс десять тысяч здоровья",
            # thousands before the stats players count in thousands, and before «до», «или», «и», a dash
            "5 к дпс": "пять тысяч дэ пэ +эс", "2 к хпс": "две тысячи хпс", "2 к гс": "две тысячи гс",
            "5 к чести": "пять тысяч чести", "20 к репы": "двадцать тысяч репы", "20 к рейта": "двадцать тысяч рейта",
            "5 к хила": "пять тысяч хила", "от 5 к до 10 к": "от пяти тысяч до десяти тысяч",
            "5 к или 10 к": "пять тысяч или десять тысяч", "5 к - 10 к": "пять тысяч - десять тысяч",
            "5 к и 10 к": "пять тысяч и десять тысяч", "5 к в час": "пять тысяч в час",
            # after a price («за», «от», «до» before the number) whatever follows but a number, and before a trade word
            "за 5 к отдам": "за пять тысяч отдам", "продам за 5 к срочно": "продам за пять тысяч срочно",
            "за 1 к 1": "за один к одному", "чарю по 5 к силе": "чарю по пять к силе", "за 5 к норм": "за пять тысяч норм",
            "нужно 5 к срочно": "нужно пять тысяч срочно", "у кого 5 к есть": "у кого пять тысяч есть",
            "3 к дд": "три к дам+агеру",                       # «дам+агеру» starts with «дам»: a whole word only
            # «репутации» is also the dative: thousands of it only in one or two digits
            "20 к репутации": "двадцать тысяч репутации", "500 к репутации": "пятьсот к репутации",
        })

    def test_health_is_counted(self):
        # «хп» after a number is an amount, never an ordinal («сотое здоровье»)
        self.check({
            "осталось 100 хп": "осталось сто здоровья", "у меня 5 хп": "у меня пять здоровья",
            "у меня 1 хп": "у меня одно здоровье", "2 хп": "два здоровья", "5 hp": "пять здоровья",
            "у босса 10к хп": "у босса десять тысяч здоровья", "10 к хп": "десять тысяч здоровья",
            "2кк хп": "два миллиона здоровья", "500 хп и 5с кд": "пятьсот здоровья и пять секунд кулд+аун",
            "хп мало": "здоровье мало",
        })

    def test_declension_off_changes_only_the_declension(self):
        # the regexes match the same with declension off: «лок40» made «уровень 40», and the «к» rule
        # must not then take «40 к» for forty thousand
        cases = {"лок40 к вам": "чернокнижник, уровень сорок к вам",
                 "дд60 к нам в пати": "дам+агер, уровень шестьдесят к нам в п+ати",
                 "у босса 10к хп": "у босса десять тысяч здоровья", "5с кд": "пять секунд кулд+аун"}
        self.check(cases)
        self.check(cases, declension=False)
        self.assertEqual(self.say("идём в ОП", declension=False), "идём в Огненная пр+опасть")

    def test_a_word_with_an_apostrophe_is_one_word(self):
        self.check({"Лок'тар огар!": "Лок'тар огар!", "За Орду! Лок’тар!": "За Орду! Лок’тар!",
                    "'лок', привет": "'чернокнижник', привет", "идём в ЗГ": "идём в Зул'Гур+уб"})

    def test_hyphenated_words_after_a_number(self):
        # the default's «рл» entries make «рейд-лидер»: a count, not «второй рейд-лидера»
        self.check({"2 рла": "два рейд-лидера", "5 рлов": "пять рейд-лидеров", "2 топ-гильдии": "две топ-гильдии"})

    def test_from_a_level_after_s(self):
        # "с" before the dictionary's ordinal is "from" (the genitive), not "with" (the instrumental)
        self.check({"инвайт с 60 лвл": "инвайт с шестидесятого уровня", "с 55 лвл": "с пятьдесят пятого уровня",
                    "со 2 лвл": "со второго уровня", "с 5 магами": "с пятью магами", "с ОП": "с Огненной пр+опастью"})

    def test_a_range_of_ordinals(self):
        # "с N по M": both number what comes after M, in its case after "по" ("по" of a range asks the accusative)
        self.check({
            "с 1 по 5 уровень": "с первого по пятый уровень", "с 10 по 20 уровень": "с десятого по двадцатый уровень",
            "с 5 по 10 лвл": "с пятого по десятый уровень", "с 1 по 3 босса": "с первого по третьего босса",
            "с 2 по 4 фазу": "со второй по четвёртую фазу", "с 1 по 3 место": "с первого по третье место",
            # no noun after it: a count, the first in the genitive
            "с 1 по 5": "с одного по пять",
            # "по" alone gives each its share, in the dative
            "дам по 5 золотых": "дам по пять золотых", "по 1 золотому": "по одному золотому",
            # a function word, a sign («+» comes from the addon as the word) or a name after M is no noun
            # of the range: a count, as before
            "рейд с 20 по 23 по мск": "рейд с двадцати по двадцать три по эм-эс-к+а",
            "с 1 по 5 и дальше": "с одного по пять и дальше", "с 1 по 5 плюс": "с одного по пять плюс",
            # a name, a place, an abbreviation (pymorphy's best reading): no noun of the range either
            "с 1 по 3 Ивана": "с одного по три Ивана", "с 1 по 3 Москву": "с одного по три Москву",
            "с 1 по 5 вов": "с одного по пять вов",
            # the noun as typed: "босс" is no accusative of the animate, so the ordinal is not one either
            "с 2 по 4 босс": "со второго по четвёртый босс",
            # M made a two-word ordinal by the dictionary: the noun's ordinal is its last word
            "с 20 по 25 лвл": "с двадцатого по двадцать пятый уровень",
            "с 1 по 25 уровень": "с первого по двадцать пятый уровень",
            "паровоз с 22 по 28 лвл": "паровоз с двадцать второго по двадцать восьмой уровень",
            "с 1 по 5 раз": "с первого по пятый раз",    # pymorphy's best reading of "раз" is plural
        })

    def test_dates(self):
        # the day of a month is a neuter ordinal: in the genitive, or in the case its preposition asks;
        # a range's end in the accusative of "по"
        self.check({
            "с 10 по 15 мая": "с десятого по пятнадцатое мая", "с 1 по 5 января": "с первого по пятое января",
            "с 2 по 4 мая": "со второго по четвёртое мая", "до 5 мая": "до пятого мая", "рейд 5 мая": "рейд пятого мая",
            "к 1 июня": "к первому июня", "на 8 марта": "на восьмое марта", "по 5 мая": "по пятое мая",
            "до 32 мая": "до тридцати двух мая",       # no day: a count
            # two days: both are dates in the same case
            "5-6 мая": "пятого-шестого мая", "до 5-6 мая": "до пятого-шестого мая", "на 5-6 мая": "на пятое-шестое мая",
            "к 1-2 июня": "к первому-второму июня", "30-32 мая": "тридцать-тридцать два мая",
        })

    def test_a_range_needs_a_number(self):
        # "с" and "по" around a word are no range: the dictionary's word after "по" is in the dative
        self.check({
            "с тобой по кд": "с тобой по кулд+ауну", "бегаю с другом по ОП": "бегаю с другом по Огненной пр+опасти",
            "идем с пати по БГ": "идём с п+ати по полю боя",
            # an ordinal typed as a word makes a range too
            "с первого по 5 лвл": "с первого по пятый уровень",
        })

    def test_a_time_after_a_preposition_is_not_a_count(self):
        self.assertTrue(self.say("до 20:00").startswith("до двадцать"))     # an hour, not "до двадцати"
        # a time with a dash: a zero after it is no range («до двадцати-пять»)
        self.check({"до 20-05": "до двадцать-ноль пять", "до 20-00": "до двадцать-ноль ноль",
                    "в 21-00 рейд": "в двадцать один-ноль ноль рейд", "с 19-00 до 23-00": "с девятнадцать-ноль ноль до двадцать три-ноль ноль",
                    "счёт 2-0": "счёт два-ноль", "до 5-10": "до пяти-десяти"})

    def test_a_count_after_a_preposition_of_the_genitive(self):
        # «5 игроков» is also the nominative count: the preposition says it is the genitive
        self.check({
            "из-за 2 боссов": "из-за двух боссов", "у 5 игроков": "у пяти игроков", "без 2 танков": "без двух танков",
            "для 3 хилов": "для трёх хилов", "до 2 часов": "до двух часов", "после 3 боссов": "после трёх боссов",
            "нет 5 игроков": "нет пяти игроков", "с 5 часов": "с пяти часов",
            "с 5 до 10": "с пяти до десяти", "с 1 до 3 ночи": "с одного до трёх ночи",   # a range
            "ждем до 10.": "ждём до десяти.",                                         # at the line's end
            # two numbers of one noun: both in the preposition's case
            "до 2-3 человек": "до двух-трёх человек", "от 5-10 минут": "от пяти-десяти минут", "до 5/5": "до пяти/пяти",
            "с 2-3 магами": "с двумя-тремя магами", "у 2-3 игроков": "у двух-трёх игроков",
            "по 2-3 человека": "по два-три человека", "5-10 минут": "пять-десять минут",
            # an hour of the day, not an ordinal
            "до 5 утра": "до пяти утра", "с 8 вечера": "с восьми вечера", "после 9 вечера": "после девяти вечера",
            "в 3 ночи": "в три ночи",
            "до 2 дня": "до двух дня", "через 2 дня": "через два дня", "осталось 2 дня": "осталось два дня",
            "для 2 дня": "для второго дня",                    # no hour after "для": the second day
            # "нет" may be an answer: the genitive only where a count cannot stand
            "нет 2 хила уже есть": "нет два хила уже есть", "нет 2 хилов": "нет двух хилов",
            "нет 2 места": "нет два места", "нет 5": "нет пять", "нет 2 танк": "нет два т+анка",
            "из-за 22 боссов": "из-за двадцати двух боссов", "из-за 25 боссов": "из-за двадцати пяти боссов",
            "у 21 игрока": "у двадцати одного игрока", "у 101 игрока": "у ста одного игрока",
            "у 1000 игроков": "у одной тысячи игроков", "без 1 руки": "без одной руки",
            # "тысяча", "миллион" are nouns: plural after any number but one
            "до 2к": "до двух тысяч", "от 3к хп": "от трёх тысяч здоровья", "до 2500": "до двух тысяч пятисот",
            "до 21000": "до двадцати одной тысячи", "до 2кк": "до двух миллионов", "о 2000 боссах": "о двух тысячах боссах",
            "от 0 до 100": "от ноля до ста",
            # the dictionary's number forms: 2-4 take the plural there too, not «для второго танка»
            "для 2 танк": "для двух т+анков", "у 2 дд": "у двух дам+агеров", "до 2%": "до двух процентов",
            # the other cases, and the nominative count
            "к 3 боссам": "к трём боссам", "о 5 боссах": "о пяти боссах", "с 5 магами": "с пятью магами",
            "убил 5 боссов": "убил пять боссов", "на 5 боссов": "на пять боссов", "за 2 часа": "за два часа",
        })

    def test_a_pair_starting_with_one(self):
        # the noun after a pair is in the form its second number asks («места» after «два»): the first, ending
        # in 1, takes only the case the preposition asks, and the noun's gender
        self.check({
            "осталось 1-2 места": "осталось одно-два места", "нужно 1-2 человека": "нужно один-два человека",
            "через 1-2 минуты": "через одну-две минуты", "на 1-2 часа": "на один-два часа",
            "21-22 уровня": "двадцать один-двадцать два уровня", "до 1-2 мест": "до одного-двух мест",
            "1-2 раза": "один-два раза", "на 1-2 места": "на одно-два места", "за 1-2 минуты": "за одну-две минуты",
            # the preposition's case where the noun is in it: «с» may ask two
            "с 1-2 магами": "с одним-двумя магами", "у 21-22 игроков": "у двадцати одного-двадцати двух игроков",
            "в 1-2 сумках": "в одной-двух сумках", "к 1-2 боссам": "к одному-двум боссам",
            "от 1-2 минут": "от одной-двух минут", "по 1-2 человека": "по одному-два человека",
            "нет 1-2 мест": "нет одного-двух мест", "нет 1-2 места": "нет одно-два места",
            # ... not where a singular after «два» is only spelt as in it («две ночи», not «на ночи»): a count, both
            "на 1-2 ночи": "на одну-две ночи", "на 1-2 части": "на одну-две части", "в 1-2 сети": "в одну-две сети",
            "на 1-2 этаже": "на одном-втором этаже",
            # where the preposition asks the genitive, a genitive singular is its own (the second numbers it)
            "с 1-2 уровня": "с одного-второго уровня",
            # a range from a pair: the genitive of «с» («с» may ask two)
            "с 1-2 до 5": "с одного-двух до пяти",
        })

    def test_a_singular_in_an_oblique_case_is_an_ordinal(self):
        # in the case a preposition asks a count of 2 or more takes the plural («до 15 мест»)
        self.check({
            "до 15 места": "до пятнадцатого м+еста", "с 2 места": "со второго м+еста", "нет 5 места": "нет пятого м+еста",
            "1 место в группу": "одно место в группу", "на 2 месте": "на втором месте", "2 места в рейд": "два места в рейд",
            "с 1 места": "с одного места", "с 21 уровня": "с двадцать первого уровня",
            # a mass is measured, not numbered: «до 200 опыта» is an amount
            "до 200 опыта": "до двухсот опыта", "без 50 маны": "без пятидесяти маны", "до 500 урона": "до пятисот урона",
            "до 5 хп": "до пяти здоровья",
            # a character's stats and materials are measured too; a number of 100 or more before a noun that
            # does not number is an amount, but a year is numbered
            "от 300 защиты": "от трёхсот защиты", "без 10 силы": "без десяти силы", "до 20 ткани": "до двадцати ткани",
            "от 5к брони": "от пяти тысяч брони", "от 300 интеллекта": "от трёхсот интеллекта",
            "до 1000 рейтинга": "до одной тысячи рейтинга", "до 2020 года": "до две тысячи двадцатого года",
            # a year numbers, ending in 1 too; the second prepositional («году», «ряду») is the prepositional
            "в 2026 году": "в две тысячи двадцать шестом году", "в 2021 году": "в две тысячи двадцать первом году",
            "с 2021 года": "с две тысячи двадцать первого года", "2021 год": "две тысячи двадцать первый год",
            "1 год": "один год", "21 год": "двадцать один год", "1000 лет": "одна тысяча лет",
            # a year in two digits too, where only an ordinal takes the prepositional; not the dative of «по»
            "в 21 году": "в двадцать первом году", "на 3 году": "на третьем году", "по 1 году": "по одному году",
            "в 2 шкафу": "во втором шкафу", "в 1 ряду": "в одном ряду", "в 5 часу утра": "в пятом часу утра",
            "с 100 уровня": "с сотого уровня", "на 3 попытке": "на третьей попытке",
            "до 225 навыка": "до двухсот двадцати пяти навыка", "150 навыка": "сто пятьдесят навыка",
            # ... in the genitive singular only: in another case a large number is a place in a row
            "100 место": "сотое место", "занял 100 место в рейтинге": "занял сотое место в рейтинге",
            "на 120 странице": "на сто двадцатой странице", "мой 100 персонаж": "мой сотый персонаж",
            "1000 игрок": "тысячный игрок", "200 золотой": "двести золотой",
            # ... and over a thousand in any case: «10к» is «10000»
            "10к танк": "десять тысяч т+анк", "10к репа": "десять тысяч репа",
            # the preposition's long form before the number's word
            "в 2 сумке": "во второй сумке", "о 11 боссах": "об одиннадцати боссах", "к 2 боссу": "ко второму боссу",
            "с 100 игроков": "со ста игроков", "с 2 магами": "с двумя магами",
        })

    def test_endings_typed_with_a_number(self):
        # an ordinal's ending agrees with the noun after it; a lone «м» with no such noun is minutes or
        # metres, not an ordinal; a cardinal's ending and «-ка» are forms of the number; «2х2» is a match
        self.check({
            "на 10й минуте": "на десятой минуте", "с 1-го по 5-й уровень": "с первого по пятый уровень",
            "на 4м этаже": "на четвёртом этаже", "в 5м ряду": "в пятом ряду", "на 2-м месте": "на втором месте",
            "до 5м": "до пяти м", "за 5м до рейда": "за пять м до рейда", "стоим в 5 м": "стоим в пять м",
            "через 5м": "через пять м", "идем в 4м": "идём вчетвером",
            "до 5ти человек": "до пяти человек", "с 3мя магами": "с тремя магами", "ходим в 40ку": "ходим в сороковку",
            "арена 2х2": "арена два на два", "5х5": "пять на пять", "3v3": "три на три", "из 2х": "из двух",
            # both numbers of a match are cardinals, whatever comes after or before them
            "2х2 арена": "два на два арена", "5х5 бг": "пять на пять поле боя", "на 2х2 арене": "на два на два арене",
            "для 2х2": "для два на два", "2 х 2": "два на два", "10 на 10 метров": "десять на десять метров",
        })

    def test_spaced_s_after_a_number_is_the_preposition(self):
        # «5 с» spaced was silver before any word; glued, or at the end of a phrase, it still is
        self.check({
            "нас 5 с хилом": "нас пять с хилом", "остался 1 на 1 с боссом": "остался один на один с боссом",
            "группа 4 с танком": "группа четыре с танком", "2 с половиной часа": "два с половиной часа",
            "2 с половиной минуты": "две с половиной минуты", "1 с половиной часа": "один с половиной часа",
            "до 2 с половиной часов": "до двух с половиной часов", "100 с лишним человек": "сто с лишним человек",
            "продам за 5 с": "продам за пять серебра", "за 5 с, срочно": "за пять серебра, срочно",
            "5с": "пять серебра", "за 2г50с": "за два золотых пятьдесят серебра", "5 с кд": "пять секунд кулд+аун",
        })

    def test_a_dative_after_k_is_the_preposition_after_a_price_too(self):
        self.check({
            "чант до 5 к силе": "чант до пяти к силе", "до 10 к урону": "до десяти к урону",
            "до 5 к вечеру буду": "до пяти к вечеру буду", "от 5 к нам идут": "от пяти к нам идут",
            "за 5 к отдам": "за пять тысяч отдам", "продам за 5 к": "продам за пять тысяч",
        })

    def test_a_move_goes_between_places_not_counts(self):
        self.check({
            "перешли с 10 на 25 человек": "перешли с десяти на двадцать пять человек",
            "перенос с 20 на 21 час": "перенос с двадцати на двадцать один час",
            "с 2 на 3 место": "со второго на третье место", "со 2 на 3 фазу": "со второй на третью фазу",
            # a place outside any list moves by its form: a count of M would say «две группы», «три сервера»
            "пересел с 1 на 2 группу": "пересел с первой на вторую группу",
            "перейди со 2 на 3 группу": "перейди со второй на третью группу",
            "перешел с 1 на 3 сервер": "перешёл с первого на третий сервер", "с 1 на 2 канал": "с первого на второй канал",
            "с 2 на 3 раунд": "со второго на третий раунд", "с 1 на 2 точку": "с первой на вторую точку",
            "с 5 на 6 группу": "с пятой на шестую группу", "с 19 на 20 часов": "с девятнадцати на двадцать часов",
            "с 2 на 3 босса": "с двух на три босса", "с 1 на 2 часа": "с одного на два часа",
            "с 20 на 21 уровень": "с двадцатого на двадцать первый уровень",
        })

    def test_unequal_numbers_around_na_are_no_match(self):
        # a match or a size is two equal numbers; two different ones are a count and a place, or a move
        self.check({
            "40 на 40 альтерак": "сорок на сорок альтерак", "5 на 5 бг": "пять на пять поле боя",
            "2 на 2 босса": "два на два босса",
            "нас 3 на 2 боссе": "нас три на втором боссе", "вайп 5 на 3 боссе": "в+айп пять на третьем боссе",
            "нас 5 на 2 этаже": "нас пять на втором этаже", "1 на 2 фазе": "один на второй фазе",
            # a move «с N на M»: both ordinals of a noun no count takes in that form
            "с 2 на 3 место": "со второго на третье место", "поднялся с 10 на 5 место": "поднялся с десятого на пятое место",
            "перешел с 2 на 3 фазу": "перешёл со второй на третью фазу", "с 5 на 6 лвл": "с пятого на шестой уровень",
            # ... else counts, the first in the genitive: an animate noun's accusative is a count's genitive
            "с 2 на 3 босса": "с двух на три босса", "апнул с 59 на 60": "апнул с пятидесяти девяти на шестьдесят",
            # no M typed: no move («на работу» is no place in a row)
            "ушел с 3 на работу": "ушёл с трёх на работу",
        })

    def test_a_multiplier(self):
        self.check({"х2 опыт": "икс два опыт", "x2 опыт": "икс два опыт", "х3": "икс три", "лок40 х2": "чернокнижник, уровень сорок икс два",
                    "уровень 40 х2": "уровень сорок икс два"})        # a match is glued or spaced on both sides

    def test_emoji_codes_go_before_the_dictionary(self):
        # a code's word is no dictionary entry («:lol:» became «:л+ол:», no code any more); «:+1:» comes
        # from the addon as «: плюс 1:»
        self.check({":lol: смешно": "смешно", "ок : плюс 1:": "окей", ":-1: не пойду": "не пойду",
                    "ок :handshake:": "окей", "ссылка:lol": "ссылка:л+ол"})

    def test_plus_minus(self):
        # «+-» comes from the addon as «плюс -»: «плюс-минус», before a number too
        self.check({"плюс -5 минут": "плюс-минус пять минут", "плюс -5%": "плюс-минус пять процентов",
                    "плюс - норм": "плюс-минус норм", "плюс 5 урона": "плюс пять урона"})

    def test_raid_leader_after_a_number(self):
        # «рл» after a number is the raid leader, not the ruins of Lordaeron
        self.check({"нужен 1 рл": "нужен один рейд-лидер", "нужно 2 рл": "нужно два рейд-лидера",
                    "нужно 5 рл": "нужно пять рейд-лидеров", "у 2 рл": "у двух рейд-лидеров",
                    "идём в рл": "идём в ру+ины Лордер+она"})


class PlayerStop(unittest.TestCase):
    def test_stop_drops_queued_and_late_lines(self):
        from bv.audio import Player, wav
        p = Player()
        data = wav(b"\0\0" * 100, 22050)
        made_before_stop = p.generation
        p.play(data)
        p.play(data)
        p.stop()
        self.assertTrue(p.items.empty())
        p.play(data, made_before_stop)            # finished synthesising after the stop: dropped
        self.assertTrue(p.items.empty())
        p.play(data, p.generation)
        self.assertEqual(p.items.qsize(), 1)

    def test_sentence_groups(self):
        from bv.f5engine import sentence_groups
        self.assertEqual(sentence_groups("Привет. Кто идёт? Собираемся у входа."),
                         ["Привет.", "Кто идёт?", "Собираемся у входа."])
        self.assertEqual(sentence_groups("Кто в ОП? Нужен танк?"), ["Кто в ОП?", "Нужен танк?"])
        self.assertEqual(sentence_groups("Привет. Всем. Идёшь?"), ["Привет. Всем.", "Идёшь?"])


class RawText(unittest.TestCase):
    def test_raw_after_text(self):
        line = parse("\x1f".join(["party", "И", "", "", "", "", "rate=100;voice=f5;decl=1;raw=1",
                                    "продам дам+агер", "WTS дд"]).encode())
        self.assertEqual((line.text, line.raw), ("продам дам+агер", "WTS дд"))

    def test_without_raw_flag(self):
        line = parse("\x1f".join(["party", "И", "", "", "", "", "rate=100;voice=f5", "текст"]).encode())
        self.assertEqual((line.text, line.raw), ("текст", ""))

    def test_raw_cut_off_by_the_strip(self):
        # the strip trims the payload's end: the raw text may lose its tail, or be missing entirely
        line = parse("\x1f".join(["party", "И", "", "", "", "", "raw=1", "текст"]).encode())
        self.assertEqual((line.text, line.raw), ("текст", ""))


class RefCheck(unittest.TestCase):
    def test_similarity(self):
        from bv.refcheck import similarity
        text = "Возвращайся ко мне, когда соберёшь достаточно мази."
        self.assertEqual(similarity(text, "возвращайся ко мне когда соберешь достаточно мази"), 1.0)
        leaked = "нести в сердце горе. Возвращайся ко мне, когда соберёшь достаточно мази."
        self.assertLess(similarity(text, leaked), 0.85)


class Questions(unittest.TestCase):
    def test_kind(self):
        from bv.intonation import kind, question_word, stressed_vowel
        self.assertEqual(kind("Кт+о идёт?"), "wh")
        self.assertEqual(kind("Ну а где т+анк?"), "wh")
        self.assertEqual(question_word("Ну а где т+анк?"), 2)
        self.assertEqual(kind("Идёшь с н+ами?"), "yes_no")
        self.assertIsNone(kind("Идём."))
        self.assertEqual(kind("Кт+о-нибудь прода+ёт с+умки?"), "yes_no")
        self.assertEqual(kind("Ну кто-то идёт?"), "yes_no")
        self.assertEqual(stressed_vowel("Ск+олько ст+оит?", 0), (0, 4))
        self.assertEqual(stressed_vowel("Почем+у т+ы?", 0), (2, 4))
        self.assertEqual(stressed_vowel("Ну где?", 1), (1, 2))

    def test_yes_no(self):
        from bv.intonation import is_yes_no
        self.assertTrue(is_yes_no("Идёшь с нами в Мёртвые к+опи?"))
        self.assertTrue(is_yes_no("Привет. Готов ли ты?"))
        self.assertFalse(is_yes_no("Кто идёт с нами?"))
        self.assertFalse(is_yes_no("Как дела?"))
        self.assertFalse(is_yes_no("Идём в копи."))


class Volume(unittest.TestCase):
    def test_volume_option(self):
        from bv.protocol import parse
        line = parse("say\x1fВася\x1fOrc\x1f2\x1fWARRIOR\x1f\x1frate=100;vol=40;voice=f5\x1fпривет".encode())
        self.assertEqual(line.volume, 40)
        self.assertAlmostEqual(line.gain({"volume": 50}), 0.2)
        loud = parse("say\x1fВася\x1fOrc\x1f2\x1fWARRIOR\x1f\x1frate=100;vol=999;voice=f5\x1fпривет".encode())
        self.assertEqual(loud.volume, 240)                 # the slider's top (200 %) is 240 for the program
        bare = parse("say\x1fВася\x1fOrc\x1f2\x1fWARRIOR\x1f\x1frate=100;voice=f5\x1fпривет".encode())
        self.assertIsNone(bare.volume)
        self.assertAlmostEqual(bare.gain({"volume": 100}), 1.0)


class Limiter(unittest.TestCase):
    def test_soft_limit(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("numpy")
        from bv.f5engine import limit
        x = np.array([0.1, -0.5, 0.79, 1.2, -1.9, 3.0], dtype="float32")
        y = limit(x)
        self.assertTrue(np.allclose(y[:3], x[:3]))              # below the knee: untouched
        self.assertTrue(np.all(np.abs(y) <= 1.0))               # never past full scale
        self.assertTrue(abs(y[3]) < abs(y[5]))                  # louder stays louder


class NumberAgreement(unittest.TestCase):
    def setUp(self):
        try:
            import num2words  # noqa: F401
            import pymorphy3  # noqa: F401
        except ImportError:
            self.skipTest("num2words / pymorphy3")

    def test_agree(self):
        from bv.text import numbers_to_words as f
        cases = {
            "на 1 р+уку": "на одну р+уку", "без 1 руки": "без одной руки", "2 руки": "две руки",
            "на 1 мага": "на одного мага", "нужен 1 маг": "нужен один маг", "1 золотой": "один золотой",
            "по 1 золотому": "по одному золотому", "с 5 магами": "с пятью магами", "в 3 сумках": "в трёх сумках",
            "21 сумка": "двадцать одна сумка", "с 21 магом": "с двадцатью одним магом",
            "11 рук": "одиннадцать рук", "12 рук": "двенадцать рук", "22 руки": "двадцать две руки",
            "2 дамагера": "два дамагера",   # slang, unknown to pymorphy: left alone
            "за 2 часа": "за два часа", "1 hp": "один hp", "1.": "один.",
            # only an ordinal fits: a count would want a plural there
            "в лс с 15 уровня": "в лс с пятнадцатого уровня", "до 60 уровня": "до шестидесятого уровня",
            "15 уровень": "пятнадцатый уровень", "на 2 этаже": "на втором этаже", "в 5 сумке": "в пятой сумке",
            "к 60 уровню": "к шестидесятому уровню",
            # a count: plural, "сколько" with a genitive, or a word that is a count either way
            "200 опыта": "двести опыта", "на 2 уровня выше": "на два уровня выше", "5 раз": "пять раз",
            "10 человек": "десять человек",
            # a word that numbers: after a number ending in 1, and in the genitive with no preposition
            "с 21 уровня": "с двадцать первого уровня", "1 место": "одно место", "нужно 2 места": "нужно два места", "15 место": "пятнадцатое место", "21 уровень": "двадцать первый уровень",
            "хил 15 уровня": "хил пятнадцатого уровня", "на 2 боссе": "на втором боссе", "в 3 слоте": "в третьем слоте",
            "с 3 фазы": "с третьей фазы", "3 фазы": "три фазы", "убил 5 боссов": "убил пять боссов",
            "до 11 числа": "до одиннадцатого ч+исла", "2 числа": "два числа", "с 1 места": "с одного места", "на 2 месте": "на втором месте",
            # the second number of a time, a decimal or a version: neither an ordinal nor agreeing
            "20:00 сбор": "двадцать:ноль ноль сбор", "в 21:30 рейд": "в двадцать один:тридцать рейд",
            "в 20:05 сбор": "в двадцать:ноль пять сбор",      # minutes under ten as they are said
            "1.12 патч": "один.двенадцать патч", "2,5 часа": "два,пять часа",
            # a hyphenated word agrees by its last part
            "нужно 5 рейд-лидеров": "нужно пять рейд-лидеров", "2 рейд-группы": "две рейд-группы",
            "в 3 рейд-группах": "в трёх рейд-группах", "собрал 3 сет-бонуса": "собрал три сет-бонуса",
        }
        for text, spoken in cases.items():
            self.assertEqual(f(text), spoken, text)

    def test_silver_rule(self):
        from bv.dictionary import parse, plurals
        from bv.text import numbers_to_words
        rules = parse(r"~(?<!через )\b(\d+)\s*(?:с|s)\b(?!\s*(?:кд|cd))=\1 [серебро|серебра|серебра]", print)
        def say(text):
            for pattern, replacement in rules:
                text = pattern.sub(replacement, text)
            return numbers_to_words(plurals(text))
        self.assertEqual(say("продам за 1с"), "продам за одно серебро")
        self.assertEqual(say("2с"), "два серебра")
        self.assertEqual(say("15с"), "пятнадцать серебра")
        self.assertNotIn("серебр", say("через 5с кд"))   # seconds of a cooldown, not money

    def test_seconds_rules(self):
        from bv.dictionary import parse, plurals
        from bv.text import numbers_to_words
        rules = parse("\n".join([
            r"~(?<!через )\b(\d+)\s*(?:с|s)\b(?!\s*(?:кд|cd|кулд\+?аун))=\1 [серебро|серебра|серебра]",
            r"~(?<=через )(\d+)\s*(?:с|s|сек)\b=\1 [секунду|секунды|секунд]",
            r"~\b(\d+)\s*(?:с|s|сек)\b(?=\s*(?:кд|cd|кулд\+?аун)\b)=\1 [секунда|секунды|секунд]",
        ]), print)
        def say(text):
            for pattern, replacement in rules:
                text = pattern.sub(replacement, text)
            return numbers_to_words(plurals(text))
        cases = {
            "через 1с": "через одну секунду", "через 5с пул": "через пять секунд пул",
            "через 30 сек": "через тридцать секунд", "Через 2s": "Через две секунды",
            "1с кд": "одна секунда кд", "5с кд": "пять секунд кд", "10 сек cd": "десять секунд cd",
            # as it really comes: the addon has made "кд" "кулд+аун" before the regexes run
            "5с кулд+аун": "пять секунд кулд+аун", "1с кулд+аун": "одна секунда кулд+аун",
            "продам за 5с": "продам за пять серебра", "1с": "одно серебро",
        }
        for text, spoken in cases.items():
            self.assertEqual(say(text), spoken, text)


class SavedVoices(unittest.TestCase):
    def test_reads_the_addons_choice(self):
        import tempfile
        from bv.dictionary import saved_voices
        with tempfile.TemporaryDirectory() as d:
            sv = Path(d) / "_forever_" / "WTF" / "Account" / "X" / "SavedVariables"
            sv.mkdir(parents=True)
            config = {"wow_dir": str(Path(d) / "_forever_")}
            self.assertIsNone(saved_voices(config))
            (sv / "BarrensVoice.lua").write_text('BarrensVoiceDB = {\n["voices"] = "sapi",\n}\n', encoding="utf-8")
            self.assertEqual(saved_voices(config), "sapi")


class OnnxParts(unittest.TestCase):
    """What the ONNX engines do without a model - F5's vocabulary and text, the provider and models, resampling."""

    def test_vocab_and_ids(self):
        from bv.f5onnx import read_vocab, text_ids
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "vocab.txt"
            path.write_text(" \n!\n+\nа\nб\n,\n\x0b\n", encoding="utf-8")   # a space line; an odd symbol too
            vocab = read_vocab(path)
        self.assertEqual(vocab[" "], 0)
        self.assertEqual(vocab["\x0b"], 6)                       # lines split on "\n" only, as F5 reads the file
        self.assertEqual(text_ids("б+а; я", vocab).tolist(), [[4, 2, 3, 5, 0, 0]])   # ";" -> ","; unknown -> 0

    def test_clean_tail(self):
        import numpy as np
        from bv.f5onnx import clean_tail
        x = np.full(24000, 0.1, np.float32)
        x[-30:] = -1.0                                           # the burst Decode ends a line with
        out = clean_tail(x, 256, 24000)
        self.assertEqual(len(out), 24000 - 512)
        self.assertLess(float(np.abs(out).max()), 0.11)          # no false peak left for `tidy`
        self.assertEqual(float(out[-1]), 0.0)                    # faded out: nothing to click
        self.assertAlmostEqual(float(out[-241]), 0.1, places=5)  # only the last 10 ms
        self.assertEqual(len(clean_tail(x[:100], 256, 24000)), 0)

    def test_provider_and_models(self):
        from bv.f5engine import model_dir, provider
        cpu = "CPUExecutionProvider"
        self.assertEqual(provider({}, ["CUDAExecutionProvider", cpu]), "CUDAExecutionProvider")   # NVIDIA first
        self.assertEqual(provider({}, ["DmlExecutionProvider", cpu]), "DmlExecutionProvider")
        self.assertEqual(provider({}, [cpu]), cpu)
        self.assertEqual(provider({"f5_onnx_provider": cpu}, ["CUDAExecutionProvider"]), cpu)
        self.assertEqual(model_dir({"f5_onnx_dir": "E:/m"}, Path("app")), Path("E:/m"))
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(model_dir({}, Path(d)))                           # none here: from Hugging Face
            local = Path(d) / "models" / "f5-onnx"
            local.mkdir(parents=True)
            (local / "F5_Metadata.onnx").write_bytes(b"")
            self.assertEqual(model_dir({}, Path(d)), local)

    def test_share_with_game(self):
        from bv.share import tune

        class Options:
            def __init__(self):
                self.intra_op_num_threads = self.inter_op_num_threads = 0
                self.config = {}

            def add_session_config_entry(self, key, value):
                self.config[key] = value
        o = tune(None, 2, Options)
        self.assertEqual((o.intra_op_num_threads, o.inter_op_num_threads), (2, 1))
        self.assertEqual(o.config, {"session.intra_op.allow_spinning": "0", "session.inter_op.allow_spinning": "0"})
        mine = Options()
        mine.intra_op_num_threads = 6
        self.assertEqual(tune(mine, 2, Options).intra_op_num_threads, 6)       # set on purpose: kept

    def test_resample(self):
        import numpy as np
        from bv.whisper_onnx import resample
        x = np.sin(np.linspace(0, 100, 24000)).astype(np.float32)
        self.assertEqual(len(resample(x, 24000, 16000)), 16000)
        self.assertIs(resample(x, 16000, 16000).dtype, np.dtype(np.float32))


class Links(unittest.TestCase):
    """Pages the addon asks the companion to open: only its own list, the same as the addon's."""

    def test_open_known_only(self):
        from bv.links import LINKS, open_link
        opened, log = [], []
        self.assertEqual(open_link(" rhvoice ", log.append, opened.append), LINKS["rhvoice"])
        self.assertIsNone(open_link("https://evil.example", log.append, opened.append))
        self.assertEqual(opened, [LINKS["rhvoice"]])

    def test_copy_known_only(self):
        from bv.links import LINKS, copy_link
        copied, log = [], []
        self.assertEqual(copy_link("discord", log.append, copied.append), LINKS["discord"])
        self.assertIsNone(copy_link("rm -rf", log.append, copied.append))
        self.assertEqual(copied, [LINKS["discord"]])

    def test_same_as_the_addon(self):
        from bv.links import LINKS
        core = (Path(__file__).resolve().parents[2] / "addon" / "BarrensVoice" / "Core.lua").read_text(encoding="utf-8")
        block = core.split("ns.LINKS = {", 1)[1].split("\n}", 1)[0]
        addon = dict(re.findall(r'(\w+) = \{ "[^"]+", "([^"]+)" \}', block))
        self.assertEqual(addon, LINKS)


class Yo(unittest.TestCase):
    """«ё» from eyo-kernel's safe dictionary: only where «е» cannot be meant."""

    def test_restore(self):
        from bv.yo import restore
        self.assertEqual(restore("ждем на утесе, еще учеными"), "ждём на утёсе, ещё учёными")
        self.assertEqual(restore("Ждем. ЖДЕМ!"), "Ждём. ЖДЁМ!")                # the case typed is kept
        self.assertEqual(restore("все берет"), "все берет")                      # either reading is a word: left
        self.assertEqual(restore("пр+опасть, т+ебе"), "пр+опасть, т+ебе")        # the dictionary's stress: left
        self.assertEqual(restore("уже ждём"), "уже ждём")                       # typed with «ё» already
        self.assertEqual(restore("найдется кто? предмет найден"), "найдётся кто? предмет найден")
        self.assertEqual(restore("кто еще идёт? Еще один"), "кто ещё идёт? Ещё один")
        self.assertEqual(restore("ученого, ученые и ученик"), "учёного, учёные и ученик")
        self.assertEqual(restore("на утесе у Утеса Громов"), "на утёсе у Утёса Громов")

    def test_dictionary_format(self):
        # read as eyo-kernel reads it: endings in brackets; «_» - lower case only; a capital - a name only
        from bv.yo import load
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "yo.txt"
            path.write_text("# notice\nберёз(а|ы)\n_киёв\nАксён(|а)\n", encoding="utf-8")
            t = load(path)
        self.assertEqual(t["береза"], "берёза")
        self.assertEqual(t["Березы"], "Берёзы")
        self.assertEqual(t["киев"], "киёв")
        self.assertNotIn("Киев", t)
        self.assertEqual(t["Аксена"], "Аксёна")
        self.assertNotIn("аксена", t)


class Unmasking(unittest.TestCase):
    def test_disguised_letters(self):
        from bv.unmask import unmask
        self.assertEqual(unmask("xyйня какая-то"), "хуйня какая-то")          # Latin twins
        self.assertEqual(unmask("пuздец"), "пиздец")
        self.assertEqual(unmask("п0шел ты"), "пошел ты")                      # a digit inside a word
        self.assertEqual(unmask("нужно 4дд и 3 хила"), "нужно 4дд и 3 хила")  # digits at the edge stay numbers
        self.assertEqual(unmask("PvPшник WTS"), "PvPшник WTS")              # Latin without twins stays
        self.assertEqual(unmask("х*й знает"), "хуй знает")                    # asterisks
        self.assertEqual(unmask("бл**ь опять"), "блядь опять")
        self.assertEqual(unmask("на*уй"), "нахуй")
        self.assertEqual(unmask("с*ка"), "сука")
        self.assertEqual(unmask("бл*дь"), "блядь")
        self.assertEqual(unmask("бл@дь и с@ка"), "блядь и сука")              # other masking signs
        self.assertEqual(unmask("бл#ть"), "блять")
        self.assertEqual(unmask("д@вай"), "давай")                             # "@" fitting no word: an "а"
        self.assertEqual(unmask("на$уй"), "нахуй")
        self.assertEqual(unmask("50% скидка"), "50% скидка")
        self.assertEqual(unmask("с*ыр"), "с*ыр")                              # nothing fits: as it was
        self.assertEqual(unmask("5*10"), "5*10")
        # asterisks around a word are emphasis, "@" before a name a mention: no masks
        self.assertEqual(unmask("*да* я тут"), "да я тут")
        self.assertEqual(unmask("*ля* какой"), "ля какой")
        self.assertEqual(unmask("**вздыхает**"), "вздыхает")
        self.assertEqual(unmask("*бл@дь*"), "блядь")
        self.assertEqual(unmask("@Вася привет"), "Вася привет")
        self.assertEqual(unmask("@с*ка"), "сука")

    def test_plain(self):
        from bv.text import plain
        self.assertEqual(plain("кто м+ожет пом+очь с[РАЗЫСКИВАЕТСЯ: Бр+ууз]?"), "кто м+ожет пом+очь с разыскивается: Бр+ууз?")
        self.assertEqual(plain("[24] Миссия: выполнима"), "Миссия: выполнима")
        self.assertEqual(plain("идём в ОП"), "идём в оп")                    # the dictionary expands it first; else a word
        self.assertEqual(plain("ППС типо?"), "пэ-пэ-+эс типо?")              # capital consonants: letter by letter
        self.assertEqual(plain("в МВД и РЛ"), "в эм-вэ-д+э и эр-+эл")
        self.assertEqual(plain("хм, тсс"), "хм, тсс")                        # lower case: interjections stay
        try:
            import pymorphy3  # noqa: F401
        except ImportError:
            return
        self.assertEqual(plain("ЦРУ, МГУ и США"), "цэ-эр-+у, эм-гэ-+у и эс-ша-+а")   # vowels, but not syllables
        self.assertEqual(plain("в ГИБДД"), "в ги-бэ-дэ-д+э")                 # a syllable, then letters
        self.assertEqual(plain("ОМОН и ВУЗ"), "омон и ВУЗ")                  # said as words
        self.assertEqual(plain("ВСЁ, СТОЙ!"), "всё, стой!")                   # shouted words, not abbreviations

    def test_spelt_stress_is_before_a_vowel(self):
        from bv.text import apply_stress, spell
        self.assertEqual(spell("ДК"), "дэ-к+а")
        self.assertEqual(spell("ЦРУ"), "цэ-эр-+у")
        self.assertEqual(spell("СССР"), "эс-эс-эс-+эр")
        self.assertEqual(spell("ВЙ"), "вэ-й+от")
        for word in ("МВД", "ДК", "КПД", "ППС", "ХП", "ВЙ", "ВЪ"):
            for mode in ("strip", "acute"):
                self.assertNotIn("+", apply_stress(spell(word), mode), word)


class HighVoices(unittest.TestCase):
    """PSOLA on a voice above the old 500 Hz analysis ceiling (gnome women speak at 450-500 Hz)."""

    def voice(self, f0, seconds=1.6, rate=24000):
        import numpy as np
        t = np.arange(int(seconds * rate)) / rate
        wave = sum(np.sin(2 * np.pi * f0 * k * t) / k for k in range(1, 8))      # a buzz with harmonics
        return (0.2 * wave * np.minimum(1, np.minimum(t, seconds - t) / 0.05)).astype("float32"), rate

    def f0(self, x, rate, start, end):
        import numpy as np
        import parselmouth
        p = parselmouth.Sound(x[int(start * rate):int(end * rate)].astype("float64"), sampling_frequency=rate)
        f = p.to_pitch(0.01, 40, 1500).selected_array["frequency"]
        return float(np.median(f[f > 0]))

    def setUp(self):
        try:
            import parselmouth  # noqa: F401
        except ImportError:
            self.skipTest("parselmouth")

    def test_range_follows_the_voice(self):
        import parselmouth
        from bv.intonation import pitch_range
        high = parselmouth.Sound(self.voice(520)[0].astype("float64"), sampling_frequency=24000)
        low = parselmouth.Sound(self.voice(120)[0].astype("float64"), sampling_frequency=24000)
        bass = parselmouth.Sound(self.voice(52)[0].astype("float64"), sampling_frequency=24000)
        self.assertGreater(pitch_range(high)[1], 1000)
        self.assertEqual(pitch_range(low)[1], 500.0)
        self.assertLess(pitch_range(bass)[0], 50)                                   # the orc character dips to 52-55 Hz

    def test_high_and_low_voices_still_rise(self):
        from bv.intonation import shape
        for f0 in (520, 52):
            x, rate = self.voice(f0)
            y = shape(x, rate, "Идёшь с н+ами?", {"yes_no_end_db": None})
            self.assertAlmostEqual(self.f0(y, rate, 0.2, 0.6), f0, delta=f0 * 0.06)   # the body as it was
            self.assertGreater(self.f0(y, rate, 1.4, 1.55), f0 * 2 ** (5 / 12))        # the end well up

    def test_a_piece_too_short_stays_as_it_is(self):
        # Praat cannot analyse pitch in ~50 ms: the docstring's promise, unchanged, not a PraatError
        from bv.intonation import shape
        x, rate = self.voice(150, seconds=0.05)
        self.assertIs(shape(x, rate, "Идёшь с н+ами?"), x)

    def test_wh_question_peaks_on_its_word(self):
        # «Кто идёт?»: the question word, first here, is raised; the end is not
        from bv.intonation import shape
        x, rate = self.voice(150)
        y = shape(x, rate, "Кто ид+ёт?")
        self.assertEqual(len(y), len(x))
        self.assertGreater(self.f0(y, rate, 0.1, 0.4), 150 * 2 ** (3 / 12))
        self.assertAlmostEqual(self.f0(y, rate, 1.3, 1.5), 150, delta=150 * 0.06)


class SpeechSpanAndLastSyllable(unittest.TestCase):
    def test_speech_span(self):
        import numpy as np
        from bv.intonation import speech_span
        rate = 24000
        x = np.zeros(rate, dtype="float32")
        x[int(0.2 * rate):int(0.7 * rate)] = 0.5
        a, b = speech_span(x, rate)
        self.assertAlmostEqual(a, 0.2, delta=0.02)
        self.assertAlmostEqual(b, 0.7, delta=0.02)
        self.assertEqual(speech_span(x[:100], rate), (0.0, 100 / rate))                 # under one frame

    def test_a_quiet_last_syllable_is_raised(self):
        import numpy as np
        from bv.intonation import boost_last_syllable
        rate = 24000
        t = np.arange(rate) / rate
        tone = np.sin(2 * np.pi * 200 * t).astype("float32")
        x = np.zeros(rate, dtype="float32")
        x[:int(0.6 * rate)] = 0.5 * tone[:int(0.6 * rate)]                              # the body
        x[int(0.7 * rate):int(0.9 * rate)] = 0.05 * tone[:int(0.2 * rate)]              # a quiet last syllable
        y = boost_last_syllable(x, rate, below_db=4.0)
        level = lambda s: 20 * np.log10(np.sqrt(np.mean(s ** 2)))
        body, last = level(y[:int(0.6 * rate)]), level(y[int(0.72 * rate):int(0.88 * rate)])
        self.assertAlmostEqual(body - last, 4.0, delta=1.0)                             # up to 4 dB under the body
        again = boost_last_syllable(y, rate, below_db=4.0)                              # loud enough now: left alone
        self.assertLess(abs(level(again[int(0.72 * rate):int(0.88 * rate)]) - last), 0.6)


class Tempo(unittest.TestCase):
    CONFIG = {"f5_margin": 1.0, "f5_tail": 0.0, "voice_pace_blend": 0.85, "voice_pace_limit": 1.8,
              "character_tempo": 0.08}

    def seconds(self, pace, character="", **over):
        from bv.f5engine import line_seconds
        return line_seconds(pace, 0.04, 100, 100, character, {**self.CONFIG, **over})

    def test_slow_voices_drawn_toward_the_faster_quarter(self):
        slow = self.seconds(0.06)
        self.assertLess(slow, 0.06 * 100)                        # a slow voice speeds up
        self.assertGreater(slow, 0.04 * 100)                     # but stays a little slower
        self.assertAlmostEqual(self.seconds(0.02), 2.0)          # a fast one is left as it is
        self.assertAlmostEqual(self.seconds(0.04), 4.0)          # at the target: as it was
        self.assertAlmostEqual(self.seconds(0.06, voice_pace_blend=0), 6.0)
        self.assertAlmostEqual(self.seconds(0.2), 0.2 * 100 / 1.8)   # at most 1.8 times faster

    def test_each_character_has_a_tempo_of_their_own(self):
        a, b = self.seconds(0.04, "Громмаш"), self.seconds(0.04, "Тралл")
        self.assertEqual(a, self.seconds(0.04, "громмаш"))       # stable for a name
        self.assertNotEqual(a, b)
        for name in ("Громмаш", "Тралл", "Джайна", "Брэнн", "Вол'джин"):
            self.assertLessEqual(abs(self.seconds(0.04, name) / 4.0 - 1), 0.08 + 1e-9)

    def test_rate_and_margin_on_top(self):
        from bv.f5engine import line_seconds
        self.assertAlmostEqual(line_seconds(0.04, 0.04, 100, 200, "", self.CONFIG), 2.0)   # 200 % speed
        self.assertAlmostEqual(line_seconds(0.04, 0.04, 100, 100, "", {**self.CONFIG, "f5_tail": 0.5}), 4.5)

    def test_silence_after(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("numpy")
        from bv.f5engine import silence_after
        rate = 24000
        speech = np.sin(np.arange(rate) / rate * 2 * np.pi * 150).astype("float32")
        self.assertLess(silence_after(speech, rate), 0.02)                              # runs to the end
        padded = np.concatenate([speech, np.zeros(rate // 2, dtype="float32")])
        self.assertAlmostEqual(silence_after(padded, rate), 0.5, delta=0.02)


class AssignmentsFile(unittest.TestCase):
    def test_old_characters_forgotten_and_writes_batched(self):
        import json
        import tempfile
        import time
        from bv import assign
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "assignments.json"
            now = time.time()
            path.write_text(json.dumps({"давний": {"slot": "orc-male", "seen": now - assign.FORGET - 60},
                                        "недавний": {"slot": "orc-male", "seen": now - 3600}}), encoding="utf-8")
            a = Assigner(slots(), path)
            self.assertEqual(set(a.known), {"недавний"})               # not heard for 60 days: dropped
            a.flush()
            self.assertEqual(set(json.loads(path.read_text(encoding="utf-8"))), {"недавний"})
            a.slot_for("Новенький", "Orc", "2")
            self.assertNotIn("новенький", json.loads(path.read_text(encoding="utf-8")))   # not written yet
            a.flush()
            self.assertIn("новенький", json.loads(path.read_text(encoding="utf-8")))      # written on exit
            self.assertFalse(path.with_suffix(".tmp").exists())


class MergeMarks(unittest.TestCase):
    def test_a_different_split_loses_only_those_words(self):
        original = "Полуказуальная RU/UA гильдия <MIR> ищет игроков!"
        accented = "Полуказ+уальная RU / UA г+ильдия < MIR > +ищет игрок+ов!"     # RUAccent split it otherwise
        merged = merge_marks(original, accented)
        self.assertIn("игрок+ов", merged)
        self.assertIn("г+ильдия", merged)
        self.assertIn("RU/UA", merged)                                          # the text is the original's
        self.assertIn("<MIR>", merged)

    def test_dictionary_marks_win_and_case_is_kept(self):
        self.assertEqual(merge_marks("Идём в М+ёртвые КОПИ", "Ид+ём в Мёртв+ые к+опи"), "Ид+ём в М+ёртвые К+ОПИ")

    def test_spacing_from_the_original(self):
        self.assertEqual(merge_marks("помочь с[Брууз]?", "пом+очь с [Бр+ууз] ?"), "пом+очь с[Бр+ууз]?")


class SameSpeaker(unittest.TestCase):
    def test_name_dropped_when_going_on(self):
        # the companion drops a name split_name says is droppable when the same character goes on
        from bv.protocol import split_name
        self.assertEqual(split_name("Вася пишет:\x04 кто в ОП"), ("Вася пишет:", " кто в ОП", True))
        self.assertEqual(split_name("кто в ОП"), ("", "кто в ОП", False))              # names off: nothing to drop

    def test_quiet_for(self):
        import time
        from bv.audio import Player
        from bv.engines import Engines
        import queue
        import tempfile
        player = Player(8, tempfile.mkdtemp())              # not started: no thread, no winsound
        player.playing_until = time.monotonic() + 2        # a line plays two more seconds
        self.assertEqual(player.quiet_for(), 0.0)
        player.playing_until = time.monotonic() - 3        # ended three seconds ago
        self.assertAlmostEqual(player.quiet_for(), 3.0, delta=0.2)

        class Speaker:
            def __init__(self, waiting=0, working=False):
                self.lines, self.working = queue.Queue(), working
                for _ in range(waiting):
                    self.lines.put(object())
        engines = Engines.__new__(Engines)
        engines.player, engines.f5 = player, None
        engines.sapi = Speaker()
        self.assertAlmostEqual(engines.quiet_for(), 3.0, delta=0.2)
        engines.sapi = Speaker(working=True)               # a line being made: not quiet
        self.assertEqual(engines.quiet_for(), 0.0)
        engines.sapi, engines.f5 = Speaker(), Speaker(waiting=1)
        self.assertEqual(engines.quiet_for(), 0.0)


def fake_winsound(fail_first=False):
    """(the lines played - each by its last byte, a fake winsound module): the real one is Windows only."""
    import threading
    import types
    played, lock, calls = [], threading.Lock(), []

    def play_sound(path, flags):
        if path:
            calls.append(path)
            if fail_first and len(calls) == 1:
                raise RuntimeError("Failed to play sound")
            with lock:
                played.append(Path(path).read_bytes()[-1:])     # a line's last byte names it
    return played, types.SimpleNamespace(SND_FILENAME=1, SND_ASYNC=2, SND_NODEFAULT=4, PlaySound=play_sound)


def marked_line(mark: bytes, secs: float) -> bytes:
    """A silent line `secs` long whose last byte is `mark`."""
    from bv.audio import wav
    return wav(b"\0\0" * int(8000 * secs), 8000)[:-1] + mark


class PauseForCatQuest(unittest.TestCase):
    """While CatQuest speaks the player holds the lines; the line it cut is played again from its
    start, then the queue (a fake winsound: the real one is Windows only)."""

    def test_cut_line_again_then_queue(self):
        import tempfile
        import time
        played, fake = fake_winsound()
        from bv.audio import Player
        with tempfile.TemporaryDirectory() as d:
            p = Player(8, d, sound=fake)
            p.start()
            p.play(marked_line(b"A", 0.6))
            p.play(marked_line(b"B", 0.1))
            time.sleep(0.2)
            self.assertTrue(p.pause())                   # A cut
            self.assertFalse(p.pause())                  # already paused
            time.sleep(0.3)
            self.assertEqual(played, [b"A"])             # nothing more while paused
            self.assertEqual(p.quiet_for(), 0.0)
            self.assertTrue(p.resume())
            time.sleep(1.5)
            self.assertEqual(played, [b"A", b"A", b"B"])  # A again from its start, then B
            p.play(marked_line(b"C", 0.6))
            time.sleep(0.2)
            p.pause()
            p.stop()                                     # a stop during a pause: nothing comes back
            p.resume()
            time.sleep(0.8)
            self.assertEqual(played, [b"A", b"A", b"B", b"C"])

    def test_a_pause_without_resume_ends_by_itself(self):
        import tempfile
        import time
        from unittest import mock
        from bv import audio
        played, fake = fake_winsound()
        logged = []
        with tempfile.TemporaryDirectory() as d, mock.patch.object(audio, "PAUSE_MAX", 0.2):
            p = audio.Player(8, d, log=logged.append, sound=fake)
            p.start()
            p.pause()                                    # CatQuest's "resume" never comes
            p.play(marked_line(b"A", 0.1))
            time.sleep(0.2)
            self.assertEqual(played, [])
            time.sleep(1.0)                              # PAUSE_MAX later (checked every 0.5 s): on its own
            self.assertEqual(played, [b"A"])
            self.assertTrue(any(m.startswith("пауза для CatQuest дольше") for m in logged), logged)


class PlayerErrors(unittest.TestCase):
    """The player is the only one: a line that fails to play is logged and the next ones still play
    (it was the thread's end, and the companion went silent for good)."""

    def test_goes_on_after_a_failed_line(self):
        import tempfile
        import time
        played, fake = fake_winsound(fail_first=True)
        logged = []
        from bv.audio import Player
        from bv.logs import level_of
        with tempfile.TemporaryDirectory() as d:
            p = Player(2, d, log=logged.append, sound=fake)
            p.start()
            for mark in (b"A", b"B", b"C"):
                p.play(marked_line(mark, 0.05))
            time.sleep(1.0)
            self.assertTrue(p.is_alive())
            self.assertEqual(played, [b"B", b"C"])
            self.assertEqual(logged, ["не удалось проиграть строку: Failed to play sound"])
            self.assertEqual(level_of(logged[0]), "WARN")
            self.assertGreater(p.quiet_for(), 0)

    def test_its_folder_removed_meanwhile(self):
        # the folder was made only when the player was: removed (a temp cleaner) it failed every line from then on
        import shutil
        import tempfile
        import time
        played, fake = fake_winsound()
        logged = []
        from bv.audio import Player
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / "tmp"
            p = Player(2, folder, log=logged.append, sound=fake)
            p.start()
            p.play(marked_line(b"A", 0.05))
            time.sleep(0.4)
            shutil.rmtree(folder)
            p.play(marked_line(b"B", 0.05))
            time.sleep(0.4)
        self.assertEqual((played, logged), ([b"A", b"B"], []))


class CompanionStatus(unittest.TestCase):
    """The companion's word to the addon: the time in CompanionStatus.lua, read by the game at login."""

    def test_written_as_lua_the_addon_reads(self):
        import re
        import tempfile
        from bv import status
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(status.write(Path(d), now=1234567890))
            text = (Path(d) / status.FILE).read_text(encoding="utf-8")
            self.assertRegex(text, r"\nBarrensVoiceStatus = \{ beat = 1234567890 \}\n")
            self.assertTrue(status.write(Path(d), now=1234567999, stopped=True))
            self.assertIn("BarrensVoiceStatus = { beat = 0, stopped = 1234567999 }",
                          (Path(d) / "CompanionStatus.lua").read_text(encoding="utf-8"))
            self.assertFalse((Path(d) / "CompanionStatus.tmp").exists())          # written whole, then swapped in

    def test_shipped_file_matches(self):
        # the addon ships the file (so it exists when the game starts) under the same name
        from bv import status
        shipped = Path(__file__).resolve().parents[2] / "addon" / "BarrensVoice" / status.FILE
        self.assertIn("BarrensVoiceStatus = nil", shipped.read_text(encoding="utf-8"))
        toc = (shipped.parent / "BarrensVoice.toc").read_text(encoding="utf-8")
        self.assertLess(toc.index(status.FILE), toc.index("Companion.lua\n"))     # read before the module

    def test_lines_read_once_across_restarts(self):
        import tempfile
        from bv.status import SeenLines
        with tempfile.TemporaryDirectory() as d:
            seen = SeenLines(Path(d) / "seen.txt")
            self.assertFalse(seen.seen("a1-1"))
            self.assertTrue(seen.seen("a1-1"))
            self.assertFalse(seen.seen(""))
            self.assertTrue(SeenLines(Path(d) / "seen.txt").seen("a1-1"))


class ReplayQueue(unittest.TestCase):
    """/bv last: lines sent again are asked for - none dropped when the queue is full; live ones may be."""

    def line(self, text, replay=False):
        from bv.protocol import parse
        options = "rate=100" + (";replay=1" if replay else "")
        return parse("\x1f".join(["party", "Вася", "Orc", "2", "WARRIOR", "", options, text]).encode())

    def test_live_dropped_replayed_kept_in_order(self):
        import queue
        from bv.audio import queue_line
        q, said = queue.Queue(), []
        for k in range(12):                                   # a replay of 12 lines at once
            queue_line(q, self.line(f"r{k}", replay=True), 8, said.append)
        self.assertEqual(said, [])                            # none dropped
        queue_line(q, self.line("live1"), 8, said.append)     # live lines go on behind them
        queue_line(q, self.line("live2"), 8, said.append)
        texts = [q.get_nowait().text for _ in range(q.qsize())]
        self.assertEqual(texts, [f"r{k}" for k in range(12)] + ["live1", "live2"])

    def test_live_lines_keep_up(self):
        import queue
        from bv.audio import queue_line
        q, said = queue.Queue(), []
        queue_line(q, self.line("r0", replay=True), 3, said.append)
        for k in range(5):
            queue_line(q, self.line(f"l{k}"), 3, said.append)
        texts = [q.get_nowait().text for _ in range(q.qsize())]
        self.assertEqual(texts, ["r0", "l2", "l3", "l4"])     # the oldest live ones went, the replayed one stayed
        self.assertEqual(len(said), 2)

    def test_made_audio_waits_for_room(self):
        import tempfile
        import threading
        import time
        from bv.audio import Player
        p = Player(2, tempfile.mkdtemp())                     # not started: nothing plays
        p.play(b"a")
        p.play(b"b")
        done = threading.Event()
        threading.Thread(target=lambda: (p.play(b"c"), done.set()), daemon=True).start()
        time.sleep(0.2)
        self.assertFalse(done.is_set())                       # waits instead of dropping a made line
        p.items.get_nowait()                                  # one played
        self.assertTrue(done.wait(1))
        self.assertEqual([p.items.get_nowait()[1] for _ in range(p.items.qsize())], [b"b", b"c"])
        p.play(b"d")
        p.play(b"e")
        stuck = threading.Event()
        threading.Thread(target=lambda: (p.play(b"f"), stuck.set()), daemon=True).start()
        time.sleep(0.1)
        p.stop()                                              # a stop lets a waiting line go (dropped)
        self.assertTrue(stuck.wait(1))
        self.assertTrue(p.items.empty())


class StderrLog(unittest.TestCase):
    def test_lines_kept_progress_bars_collapsed(self):
        import io
        import tempfile
        from bv import __main__ as m
        with tempfile.TemporaryDirectory() as d:
            old_dir, old_file, old_day = m.LOG_DIR, m._log_file, m._log_day
            m.LOG_DIR, m._log_file, m._log_day = Path(d), None, None
            try:
                console = io.StringIO()
                err = m.StderrToLog(console)
                err.write("W1113 torch: a warning\n")
                err.write("Loading weights:   0%|    | 0/587\r")
                err.write("Loading weights:  50%|##  | 290/587\r")
                err.write("Loading weights: 100%|####| 587/587\n")
                err.write("half a li")
                err.write("ne\n")
                err.flush()
                self.assertIn("a warning", console.getvalue())                  # the console still gets it all
                self.assertIn("0/587", console.getvalue())
                m._log_file.close()
                text = next(Path(d).glob("bv-*.log")).read_text(encoding="utf-8")
                lines = [l[9:] for l in text.splitlines()]
                self.assertEqual(lines, ["DEBUG [stderr] W1113 torch: a warning",
                                         "DEBUG [stderr] Loading weights: 100%|####| 587/587",
                                         "DEBUG [stderr] half a line"])
            finally:
                if m._log_file:
                    m._log_file.close()
                m.LOG_DIR, m._log_file, m._log_day = old_dir, old_file, old_day


class RuaccentFiles(unittest.TestCase):
    def test_koziev_kept_in_the_cache(self):
        import os
        from unittest import mock
        from bv.text import keep_koziev
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"HF_HOME": str(Path(d) / "hf")}):
            package = Path(d) / "site" / "ruaccent"
            (package / "koziev").mkdir(parents=True)
            (package / "koziev" / "m.bin").write_bytes(b"x")
            keep_koziev(str(package), before=False)                     # saved from the package after a load
            self.assertTrue((Path(d) / "hf" / "ruaccent" / "koziev" / "m.bin").exists())
            fresh = Path(d) / "new-env" / "ruaccent"
            fresh.mkdir(parents=True)
            keep_koziev(str(fresh), before=True)                        # a new environment gets it back
            self.assertTrue((fresh / "koziev" / "m.bin").exists())


class SavedFlag(unittest.TestCase):
    def test_reads_the_addon_setting(self):
        from bv.dictionary import saved_flag
        with tempfile.TemporaryDirectory() as d:
            saved = Path(d) / "_forever_" / "WTF" / "Account" / "X" / "SavedVariables"
            saved.mkdir(parents=True)
            config = {"game_dirs": {"forever": str(Path(d) / "_forever_")}}
            self.assertIsNone(saved_flag(config, "fadeChat"))                      # no saved variables yet
            (saved / "BarrensVoice.lua").write_text('BarrensVoiceDB = {\n["fadeChat"] = true,\n["enabled"] = false,\n}\n',
                                                     encoding="utf-8")
            self.assertTrue(saved_flag(config, "fadeChat"))
            self.assertFalse(saved_flag(config, "enabled"))
            self.assertIsNone(saved_flag(config, "nothing"))


class ReloadHint(unittest.TestCase):
    """The /reload reminder: only for a player already in the world, with the hidden chat on, no restart."""

    def setup(self, d, fade="true", enabled="true", status=None):
        saved = Path(d) / "_forever_" / "WTF" / "Account" / "X" / "SavedVariables"
        saved.mkdir(parents=True)
        (saved / "BarrensVoice.lua").write_text(f'BarrensVoiceDB = {{\n["fadeChat"] = {fade},\n["enabled"] = {enabled},\n}}\n',
                                                 encoding="utf-8")
        addon = Path(d) / "_forever_" / "Interface" / "AddOns" / "BarrensVoice"
        addon.mkdir(parents=True)
        if status:
            (addon / "CompanionStatus.lua").write_text(f"BarrensVoiceStatus = {status}\n", encoding="utf-8")
        return {"game_dirs": {"forever": str(Path(d) / "_forever_")}}, addon

    def test_cases(self):
        from bv.reloadhint import needed
        now = 1_000_000
        cases = [  # (fade, enabled, status file, strip in view) -> remind
            (("true", "true", None, True), True),
            (("true", "true", None, False), False),                          # at character select: no
            (("false", "true", None, True), False),                          # the hidden chat off
            (("true", "false", None, True), False),                          # the addon switched off
            (("true", "true", "{ beat = 0, stopped = 999990 }", True), False),   # a restart: the addon saw the last one
            (("true", "true", "{ beat = 999000 }", True), True),             # an old beat: nobody at login
        ]
        for (fade, enabled, status, in_view), want in cases:
            with self.subTest(fade=fade, enabled=enabled, status=status, in_view=in_view):
                with tempfile.TemporaryDirectory() as d:
                    config, addon = self.setup(d, fade, enabled, status)
                    self.assertEqual(needed(config, addon, in_view=lambda c: in_view, now=now), want)


class LogLevels(unittest.TestCase):
    def test_levels(self):
        from bv.logs import level_of
        cases = {
            "игра закрыта — выхожу": "INFO",
            "окно WoW: (0, 0, 1920, 1080)": "DEBUG",
            "окно игры не найдено или свёрнуто — жду": "INFO",
            "Battle.net только что запустился и пропустил команду": "DEBUG",
            "связь с аддоном есть (ячейка 2 px)": "INFO",
            "Голоса рас готовы.": "INFO",
            "[гильдия] Громмаш (Orc, м) → orc-male/standard: всем привет": "CHAT",
            "    к синтезу: всем прив+ет.": "DEBUG",
            "[диагностика аддона] строка не отправлена": "DEBUG",
            "загружаю RUAccent ...": "DEBUG",
            "словарь (стандартный): записей 251": "DEBUG",
            "полоска аддона пропала (выключен, свёрнут или скрыт интерфейс?)": "WARN",
            "Голоса рас недоступны, читаю голосами Windows.": "WARN",
            "ОШИБКА (программа): KeyError: 1": "ERROR",
            "F5-TTS: CUDA out of memory": "ERROR",
        }
        for message, level in cases.items():
            self.assertEqual(level_of(message), level, message)

    def test_parse(self):
        from bv.logs import parse
        self.assertEqual(parse("03:12:01 INFO  окно WoW: x"), ("03:12:01", "INFO", "окно WoW: x"))
        self.assertEqual(parse("03:12:01 CHAT  [гильдия] a: b"), ("03:12:01", "CHAT", "[гильдия] a: b"))
        self.assertEqual(parse("Traceback (most recent call last):"), ("", "DEBUG", "Traceback (most recent call last):"))


class AddonMissing(unittest.TestCase):
    def test_stops_without_the_addon(self):
        import tempfile
        from unittest import mock
        from bv import voicelist
        with tempfile.TemporaryDirectory() as d:
            game = Path(d) / "_forever_"
            (game / "Interface" / "AddOns").mkdir(parents=True)
            with mock.patch("bv.voicelist.wow_roots", return_value=[game]):
                message = voicelist.missing_addon({})
                self.assertIn("не установлен", message)
                self.assertIn(str(game), message)                 # where it looked
                addon = game / "Interface" / "AddOns" / "BarrensVoice"
                addon.mkdir()
                (addon / "BarrensVoice.toc").write_text("## Title: Barrens Voice\n", encoding="utf-8")
                self.assertIsNone(voicelist.missing_addon({}))
            with mock.patch("bv.voicelist.wow_roots", return_value=[Path(d) / "nowhere"]):
                self.assertIn("папка игры тоже не найдена", voicelist.missing_addon({}))



class GameChoice(unittest.TestCase):
    """Forever by default; retail by config or --retail: only that game's folders, launcher and bank."""

    def test_folders_bank_and_product(self):
        from unittest import mock
        from bv import gamevoices, launch
        from bv.dictionary import game_of, wow_roots
        self.assertEqual(game_of({}), "forever")
        self.assertEqual(game_of({"game": "Retail"}), "retail")
        self.assertEqual(game_of({"game": "classic"}), "forever")             # unknown: the default
        self.assertTrue(all(r.name == "_forever_" for r in wow_roots({})))
        self.assertTrue(all(r.name == "_retail_" for r in wow_roots({"game": "retail"})))
        self.assertEqual(gamevoices.bank_dir({}, Path("app")), Path("app/voices"))
        self.assertEqual(gamevoices.bank_dir({"game": "retail"}, Path("app")), Path("app/voices-retail"))
        with mock.patch("bv.launch.find_battlenet", return_value=Path("bn.exe")), \
             mock.patch("bv.launch.subprocess.Popen") as popen:
            launch.launch({"game": "retail"}, lambda *a: None)
            self.assertIn("--exec=launch WoW", popen.call_args[0][0])
            launch.launch({}, lambda *a: None)
            self.assertIn("--exec=launch WoWF", popen.call_args[0][0])
            # the player started the game meanwhile (while the voice bank was built): no second game
            popen.reset_mock()
            said = []
            self.assertFalse(launch.launch({}, said.append, game_running=lambda: True))
            popen.assert_not_called()
            self.assertIn("уже запущена", said[0])


class ColdBattlenet(unittest.TestCase):
    """Battle.net started by the launch command drops it: sent once more when its window is up."""

    def run_case(self, game_at=None, window_at=None):
        from bv.launch import follow_cold_start
        clock, sent, said = [0.0], [], []

        def sleep(s):
            clock[0] += s
        ok = follow_cold_start(lambda: sent.append(clock[0]), said.append,
                               game_running=lambda: game_at is not None and clock[0] >= game_at,
                               ready=lambda: window_at is not None and clock[0] >= window_at,
                               sleep=sleep, clock=lambda: clock[0])
        return ok, sent, said

    def test_resent_once_when_the_window_is_up(self):
        ok, sent, said = self.run_case(game_at=40, window_at=20)
        self.assertTrue(ok)
        self.assertEqual(sent, [25.0])                         # 5 s after the window, once
        self.assertIn("пропустил команду", said[0])

    def test_game_came_by_itself(self):
        ok, sent, _ = self.run_case(game_at=10, window_at=8)
        self.assertTrue(ok)
        self.assertEqual(sent, [])                             # it came during the 5 s wait: nothing sent

    def test_no_window_a_minute_then_once(self):
        ok, sent, said = self.run_case()
        self.assertFalse(ok)
        self.assertEqual(len(sent), 1)                         # never twice: a second game is worse
        self.assertIn("не запустил игру", said[-1])


class EndingHeard(unittest.TestCase):
    def test_cut_and_whole(self):
        from bv.f5engine import ending_heard
        self.assertTrue(ending_heard("Всем пока.", " Всем пока!"))
        self.assertTrue(ending_heard("Ищу группу на мёртвые к+опи.", "Ищу группу на мертвые копии."))   # letters added
        self.assertTrue(ending_heard("Нужен танк в ульдам+ан.", "Нужен танк вульдаман."))             # run together
        self.assertTrue(ending_heard("Продам за пять тысяч.", "Продам за 5000."))                      # digits
        self.assertFalse(ending_heard("Ладно, я пошёл спать, всем пока.", "Ладно, я пошёл спать. Всем по-"))
        self.assertTrue(ending_heard("Г+о в р+ейд.", "Говрейт."))                     # spelled as heard
        self.assertTrue(ending_heard("Агр на мн+е, х+ильте.", "Агр на мне, Хильти."))
        self.assertFalse(ending_heard("Окей.", "Ак"))
        self.assertFalse(ending_heard("Ладно, я пошёл спать, всем пока.", "Ладно, я пошёл спать. Всем по"))
        self.assertFalse(ending_heard("да", ""))
        self.assertTrue(ending_heard("", "что-то"))


class ChatNumbers(unittest.TestCase):
    """Lines read wrong in a game session (17.11.2026), as the addon sends them («+» is the word «плюс»)."""

    def test_numbers(self):
        from bv.text import numbers_to_words as f
        self.assertEqual(f("От 50 плюс уровень"), "От пятидесяти плюс уровень")
        self.assertEqual(f("на 3 плюс человек"), "на три плюс человек")
        self.assertEqual(f("18 плюс"), "восемнадцать плюс")
        self.assertEqual(f("с 2007го"), "с две тысячи седьмого")
        self.assertEqual(f("После 40го"), "После сорокового")
        self.assertEqual(f("идем в 4м"), "идем вчетвером")
        self.assertEqual(f("на 4м этаже"), "на четвёртом этаже")
        self.assertEqual(f("из 2х"), "из двух")
        self.assertEqual(f("за 200ХП?"), "за двести ХП?")

    def test_emoji_code_and_stress_only_entry(self):
        from bv.text import plain
        self.assertEqual(plain("ок :handshake:"), "ок")
        from bv.morph import Inflector
        inflector = Inflector(print)
        self.assertEqual(inflector.apply("для \x02к+ача\x03"), "для к+ача")        # slang, not the town Кача
        self.assertEqual(inflector.apply("в \x02Огненная пр+опасть\x03"), "в Огненную пр+опасть")
        self.assertEqual(inflector.apply("для \x02дам+агер\x03"), "для дам+агера")


class LiveSettings(unittest.TestCase):
    def test_exit_with_wow_changed_while_running(self):
        # «Закрываться вместе с игрой» unchecked during the game: the running companion takes it at once
        import json
        import os
        import tempfile
        from bv.__main__ import LiveConfig
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            path.write_text(json.dumps({"exit_with_wow": True, "rate": 1}), encoding="utf-8")
            config = {"exit_with_wow": True, "rate": 1}
            live = LiveConfig(config, path)
            live.refresh()
            self.assertTrue(config["exit_with_wow"])
            path.write_text(json.dumps({"exit_with_wow": False, "rate": 5}), encoding="utf-8")
            os.utime(path, (1, 1))                                     # a new stamp, whatever the clock's grain
            live.refresh()
            self.assertEqual((config["exit_with_wow"], config["rate"]), (False, 1))   # only the live keys


if __name__ == "__main__":
    unittest.main()
