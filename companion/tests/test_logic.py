"""Text, voice assignment and payload parsing (no Windows, no GPU)."""
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wcv.assign import Assigner  # noqa: E402
from wcv.dictionary import parse as parse_rules, unescape  # noqa: E402
from wcv.gamevoices import Slot  # noqa: E402
from wcv.protocol import parse  # noqa: E402
from wcv.speech import sapi_rate  # noqa: E402
from wcv.text import apply_stress, merge_marks  # noqa: E402


class Text(unittest.TestCase):
    def test_quest_number_dropped(self):
        from wcv.text import plain
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


if __name__ == "__main__":
    unittest.main()


class VoiceListFile(unittest.TestCase):
    def test_render(self):
        from wcv.voicelist import label, render

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
        from wcv.dictionary import plurals
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
        from wcv.speech import Speaker, Voice
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
    ADDON = Path(__file__).resolve().parents[2] / "addon" / "WowChatVoice"

    def book(self, addon=None):
        from wcv.dictionary import Dictionary
        d = Dictionary({}, lambda *a: None, addon or self.ADDON)
        d.user_path = Path("/nonexistent")                 # no saved variables in the tests
        d.from_addon = "test"
        d.refresh()
        return d

    def test_rl(self):
        # «РЛ»: the Ruins of Lordaeron, unless the words around it say it is the raid leader
        from wcv.morph import Inflector
        d, inf = self.book(), Inflector(print)

        def read(text):
            return inf.apply(d.apply(inf.apply(d.apply_words(text)), mark=True))
        self.assertEqual(read("встречаемся в РЛ"), "встречаемся в ру+ины Лордер+она")
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
        from wcv.dictionary import plurals
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
        from wcv.dictionary import Dictionary
        with tempfile.TemporaryDirectory() as dd:
            path = Path(dd) / "WowChatVoice.lua"
            path.write_text('WowChatVoiceDB = {\n["dictionaryUser"] = "лок=лок\\n!ОП=Огненная пропасть",\n}\n',
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
            addon = Path(dd) / "WowChatVoice"
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

    def test_names_kept_out(self):
        from wcv.protocol import split_name, without_repeated_name
        self.assertEqual(split_name("Лок пишет:\x04 привет"), ("Лок пишет:", " привет", True))
        self.assertEqual(split_name("Лок\x05 смеётся"), ("Лок", " смеётся", False))
        self.assertEqual(split_name("привет"), ("", "привет", False))
        self.assertEqual(without_repeated_name("Лок\x05 смеётся", True), "Лок смеётся")   # an emote keeps it


class PlayerStop(unittest.TestCase):
    def test_stop_drops_queued_and_late_lines(self):
        from wcv.audio import Player, wav
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
        from wcv.f5engine import sentence_groups
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
        from wcv.refcheck import similarity
        text = "Возвращайся ко мне, когда соберёшь достаточно мази."
        self.assertEqual(similarity(text, "возвращайся ко мне когда соберешь достаточно мази"), 1.0)
        leaked = "нести в сердце горе. Возвращайся ко мне, когда соберёшь достаточно мази."
        self.assertLess(similarity(text, leaked), 0.85)


class Questions(unittest.TestCase):
    def test_kind(self):
        from wcv.intonation import kind, question_word, stressed_vowel
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
        from wcv.intonation import is_yes_no
        self.assertTrue(is_yes_no("Идёшь с нами в Мёртвые к+опи?"))
        self.assertTrue(is_yes_no("Привет. Готов ли ты?"))
        self.assertFalse(is_yes_no("Кто идёт с нами?"))
        self.assertFalse(is_yes_no("Как дела?"))
        self.assertFalse(is_yes_no("Идём в копи."))


class Volume(unittest.TestCase):
    def test_volume_option(self):
        from wcv.protocol import parse
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
        from wcv.f5engine import limit
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
        from wcv.text import numbers_to_words as f
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
        }
        for text, spoken in cases.items():
            self.assertEqual(f(text), spoken, text)

    def test_silver_rule(self):
        from wcv.dictionary import parse, plurals
        from wcv.text import numbers_to_words
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
        from wcv.dictionary import parse, plurals
        from wcv.text import numbers_to_words
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
        from wcv.dictionary import saved_voices
        with tempfile.TemporaryDirectory() as d:
            sv = Path(d) / "_forever_" / "WTF" / "Account" / "X" / "SavedVariables"
            sv.mkdir(parents=True)
            config = {"wow_dir": str(Path(d) / "_forever_")}
            self.assertIsNone(saved_voices(config))
            (sv / "WowChatVoice.lua").write_text('WowChatVoiceDB = {\n["voices"] = "sapi",\n}\n', encoding="utf-8")
            self.assertEqual(saved_voices(config), "sapi")


class OnnxParts(unittest.TestCase):
    """0.4.0: what the ONNX engines do without a model - F5's vocabulary and text, the switch, resampling."""

    def test_vocab_and_ids(self):
        from wcv.f5onnx import read_vocab, text_ids
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "vocab.txt"
            path.write_text(" \n!\n+\nа\nб\n,\n\x0b\n", encoding="utf-8")   # a space line; an odd symbol too
            vocab = read_vocab(path)
        self.assertEqual(vocab[" "], 0)
        self.assertEqual(vocab["\x0b"], 6)                       # lines split on "\n" only, as F5 reads the file
        self.assertEqual(text_ids("б+а; я", vocab).tolist(), [[4, 2, 3, 5, 0, 0]])   # ";" -> ","; unknown -> 0

    def test_backend_switch(self):
        from wcv.f5engine import onnx_backend
        self.assertFalse(onnx_backend({}))
        self.assertTrue(onnx_backend({"f5_backend": "ONNX"}))

    def test_resample(self):
        import numpy as np
        from wcv.whisper_onnx import resample
        x = np.sin(np.linspace(0, 100, 24000)).astype(np.float32)
        self.assertEqual(len(resample(x, 24000, 16000)), 16000)
        self.assertIs(resample(x, 16000, 16000).dtype, np.dtype(np.float32))


class Links(unittest.TestCase):
    """Pages the addon asks the companion to open: only its own list, the same as the addon's."""

    def test_open_known_only(self):
        from wcv.links import LINKS, open_link
        opened, log = [], []
        self.assertEqual(open_link(" rhvoice ", log.append, opened.append), LINKS["rhvoice"])
        self.assertIsNone(open_link("https://evil.example", log.append, opened.append))
        self.assertEqual(opened, [LINKS["rhvoice"]])

    def test_copy_known_only(self):
        from wcv.links import LINKS, copy_link
        copied, log = [], []
        self.assertEqual(copy_link("discord", log.append, copied.append), LINKS["discord"])
        self.assertIsNone(copy_link("rm -rf", log.append, copied.append))
        self.assertEqual(copied, [LINKS["discord"]])

    def test_same_as_the_addon(self):
        from wcv.links import LINKS
        core = (Path(__file__).resolve().parents[2] / "addon" / "WowChatVoice" / "Core.lua").read_text(encoding="utf-8")
        block = core.split("ns.LINKS = {", 1)[1].split("\n}", 1)[0]
        addon = dict(re.findall(r'(\w+) = \{ "[^"]+", "([^"]+)" \}', block))
        self.assertEqual(addon, LINKS)


class Yo(unittest.TestCase):
    """«ё» from eyo-kernel's safe dictionary: only where «е» cannot be meant."""

    def test_restore(self):
        from wcv.yo import restore
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
        from wcv.yo import load
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
        from wcv.unmask import unmask
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

    def test_plain(self):
        from wcv.text import plain
        self.assertEqual(plain("кто м+ожет пом+очь с[РАЗЫСКИВАЕТСЯ: Бр+ууз]?"), "кто м+ожет пом+очь с разыскивается: Бр+ууз?")
        self.assertEqual(plain("[24] Миссия: выполнима"), "Миссия: выполнима")
        self.assertEqual(plain("идём в ОП"), "идём в оп")                    # the dictionary expands it first; else a word
        self.assertEqual(plain("ППС типо?"), "пэ-пэ-+эс типо?")              # capital consonants: letter by letter
        self.assertEqual(plain("в МВД и РЛ"), "в эм-вэ-+дэ и эр-+эл")
        self.assertEqual(plain("хм, тсс"), "хм, тсс")                        # lower case: interjections stay
        try:
            import pymorphy3  # noqa: F401
        except ImportError:
            return
        self.assertEqual(plain("ЦРУ, МГУ и США"), "цэ-эр-+у, эм-гэ-+у и эс-ша-+а")   # vowels, but not syllables
        self.assertEqual(plain("в ГИБДД"), "в ги-бэ-дэ-+дэ")                 # a syllable, then letters
        self.assertEqual(plain("ОМОН и ВУЗ"), "омон и ВУЗ")                  # said as words
        self.assertEqual(plain("ВСЁ, СТОЙ!"), "всё, стой!")                   # shouted words, not abbreviations


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
        from wcv.intonation import pitch_range
        high = parselmouth.Sound(self.voice(520)[0].astype("float64"), sampling_frequency=24000)
        low = parselmouth.Sound(self.voice(120)[0].astype("float64"), sampling_frequency=24000)
        bass = parselmouth.Sound(self.voice(52)[0].astype("float64"), sampling_frequency=24000)
        self.assertGreater(pitch_range(high)[1], 1000)
        self.assertEqual(pitch_range(low)[1], 500.0)
        self.assertLess(pitch_range(bass)[0], 50)                                   # the orc character dips to 52-55 Hz

    def test_high_and_low_voices_still_rise(self):
        from wcv.intonation import shape
        for f0 in (520, 52):
            x, rate = self.voice(f0)
            y = shape(x, rate, "Идёшь с н+ами?", {"yes_no_end_db": None})
            self.assertAlmostEqual(self.f0(y, rate, 0.2, 0.6), f0, delta=f0 * 0.06)   # the body as it was
            self.assertGreater(self.f0(y, rate, 1.4, 1.55), f0 * 2 ** (5 / 12))        # the end well up


class Tempo(unittest.TestCase):
    CONFIG = {"f5_margin": 1.0, "f5_tail": 0.0, "voice_pace_blend": 0.85, "voice_pace_limit": 1.8,
              "character_tempo": 0.08}

    def seconds(self, pace, character="", **over):
        from wcv.f5engine import line_seconds
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
        from wcv.f5engine import line_seconds
        self.assertAlmostEqual(line_seconds(0.04, 0.04, 100, 200, "", self.CONFIG), 2.0)   # 200 % speed
        self.assertAlmostEqual(line_seconds(0.04, 0.04, 100, 100, "", {**self.CONFIG, "f5_tail": 0.5}), 4.5)

    def test_silence_after(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("numpy")
        from wcv.f5engine import silence_after
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
        from wcv import assign
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
        from wcv.protocol import without_repeated_name
        self.assertEqual(without_repeated_name("Вася пишет:\x04 кто в ОП", True), "кто в ОП")
        self.assertEqual(without_repeated_name("Вася пишет:\x04 кто в ОП", False), "Вася пишет: кто в ОП")
        self.assertEqual(without_repeated_name("кто в ОП", True), "кто в ОП")              # names off: nothing to drop

    def test_quiet_for(self):
        import time
        from wcv.audio import Player
        from wcv.engines import Engines
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


class PauseForCatQuest(unittest.TestCase):
    """While CatQuest speaks the player holds the lines; the line it cut is played again from its
    start, then the queue (a fake winsound: the real one is Windows only)."""

    def test_cut_line_again_then_queue(self):
        import sys
        import tempfile
        import threading
        import time
        import types
        played, lock = [], threading.Lock()
        fake = types.SimpleNamespace(SND_FILENAME=1, SND_ASYNC=2, SND_NODEFAULT=4)
        def play_sound(path, flags):
            if path:
                with lock:
                    played.append(Path(path).read_bytes()[-1:])     # a line's last byte names it
        fake.PlaySound = play_sound
        sys.modules["winsound"] = fake
        from wcv.audio import Player, wav
        def line(mark, secs):
            return wav(b"\0\0" * int(8000 * secs), 8000)[:-1] + mark
        with tempfile.TemporaryDirectory() as d:
            p = Player(8, d)
            p.start()
            p.play(line(b"A", 0.6))
            p.play(line(b"B", 0.1))
            time.sleep(0.2)
            self.assertTrue(p.pause())                   # A cut
            self.assertFalse(p.pause())                  # already paused
            time.sleep(0.3)
            self.assertEqual(played, [b"A"])             # nothing more while paused
            self.assertEqual(p.quiet_for(), 0.0)
            self.assertTrue(p.resume())
            time.sleep(1.5)
            self.assertEqual(played, [b"A", b"A", b"B"])  # A again from its start, then B
            p.play(line(b"C", 0.6))
            time.sleep(0.2)
            p.pause()
            p.stop()                                     # a stop during a pause: nothing comes back
            p.resume()
            time.sleep(0.8)
            self.assertEqual(played, [b"A", b"A", b"B", b"C"])


class CompanionStatus(unittest.TestCase):
    """The companion's word to the addon: the time in CompanionStatus.lua, read by the game at login."""

    def test_written_as_lua_the_addon_reads(self):
        import re
        import tempfile
        from wcv import status
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(status.write(Path(d), now=1234567890))
            text = (Path(d) / status.FILE).read_text(encoding="utf-8")
            self.assertRegex(text, r"\nWowChatVoiceStatus = \{ beat = 1234567890 \}\n")
            self.assertFalse((Path(d) / "CompanionStatus.tmp").exists())          # written whole, then swapped in

    def test_shipped_file_matches(self):
        # the addon ships the file (so it exists when the game starts) under the same name
        from wcv import status
        shipped = Path(__file__).resolve().parents[2] / "addon" / "WowChatVoice" / status.FILE
        self.assertIn("WowChatVoiceStatus = nil", shipped.read_text(encoding="utf-8"))
        toc = (shipped.parent / "WowChatVoice.toc").read_text(encoding="utf-8")
        self.assertLess(toc.index(status.FILE), toc.index("Companion.lua\n"))     # read before the module

    def test_lines_read_once_across_restarts(self):
        import tempfile
        from wcv.status import SeenLines
        with tempfile.TemporaryDirectory() as d:
            seen = SeenLines(Path(d) / "seen.txt")
            self.assertFalse(seen.seen("a1-1"))
            self.assertTrue(seen.seen("a1-1"))
            self.assertFalse(seen.seen(""))
            self.assertTrue(SeenLines(Path(d) / "seen.txt").seen("a1-1"))


class ReplayQueue(unittest.TestCase):
    """/wcv last: lines sent again are asked for - none dropped when the queue is full; live ones may be."""

    def line(self, text, replay=False):
        from wcv.protocol import parse
        options = "rate=100" + (";replay=1" if replay else "")
        return parse("\x1f".join(["party", "Вася", "Orc", "2", "WARRIOR", "", options, text]).encode())

    def test_live_dropped_replayed_kept_in_order(self):
        import queue
        from wcv.audio import queue_line
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
        from wcv.audio import queue_line
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
        from wcv.audio import Player
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
        from wcv import __main__ as m
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
                text = next(Path(d).glob("wcv-*.log")).read_text(encoding="utf-8")
                lines = [l[9:] for l in text.splitlines()]
                self.assertEqual(lines, ["[stderr] W1113 torch: a warning",
                                         "[stderr] Loading weights: 100%|####| 587/587", "[stderr] half a line"])
            finally:
                if m._log_file:
                    m._log_file.close()
                m.LOG_DIR, m._log_file, m._log_day = old_dir, old_file, old_day


class AddonMissing(unittest.TestCase):
    def test_stops_without_the_addon(self):
        import tempfile
        from unittest import mock
        from wcv import voicelist
        with tempfile.TemporaryDirectory() as d:
            game = Path(d) / "_forever_"
            (game / "Interface" / "AddOns").mkdir(parents=True)
            with mock.patch("wcv.voicelist.wow_roots", return_value=[game]):
                message = voicelist.missing_addon({})
                self.assertIn("не установлен", message)
                self.assertIn(str(game), message)                 # where it looked
                addon = game / "Interface" / "AddOns" / "WowChatVoice"
                addon.mkdir()
                (addon / "WowChatVoice.toc").write_text("## Title: WoW Chat Voice\n", encoding="utf-8")
                self.assertIsNone(voicelist.missing_addon({}))
            with mock.patch("wcv.voicelist.wow_roots", return_value=[Path(d) / "nowhere"]):
                self.assertIn("папка игры тоже не найдена", voicelist.missing_addon({}))



class GameChoice(unittest.TestCase):
    """Forever by default; retail by config or --retail: only that game's folders, launcher and bank."""

    def test_folders_bank_and_product(self):
        from unittest import mock
        from wcv import gamevoices, launch
        from wcv.dictionary import game_of, wow_roots
        self.assertEqual(game_of({}), "forever")
        self.assertEqual(game_of({"game": "Retail"}), "retail")
        self.assertEqual(game_of({"game": "classic"}), "forever")             # unknown: the default
        self.assertTrue(all(r.name == "_forever_" for r in wow_roots({})))
        self.assertTrue(all(r.name == "_retail_" for r in wow_roots({"game": "retail"})))
        self.assertEqual(gamevoices.bank_dir({}, Path("app")), Path("app/voices"))
        self.assertEqual(gamevoices.bank_dir({"game": "retail"}, Path("app")), Path("app/voices-retail"))
        with mock.patch("wcv.launch.find_battlenet", return_value=Path("bn.exe")), \
             mock.patch("wcv.launch.subprocess.Popen") as popen:
            launch.launch({"game": "retail"}, lambda *a: None)
            self.assertIn("--exec=launch WoW", popen.call_args[0][0])
            launch.launch({}, lambda *a: None)
            self.assertIn("--exec=launch WoWF", popen.call_args[0][0])
