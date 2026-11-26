"""Text, voice assignment and payload parsing (no Windows, no GPU)."""
import os
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

    def test_ruaccent_reads_the_line_in_lower_case(self):
        # a capital makes RUAccent take a word for a name: it gets the line in lower case, the marks go back onto the
        # text as written; the dictionary's marks still win
        from bv.text import Accentor
        seen = []

        class Model:
            def process_all(self, text):
                seen.append(text)
                return text.replace("придержите", "придерж+ите").replace("пиво", "п+иво").replace("подгород", "подгор+од")
        accentor = Accentor(print)
        accentor.model = Model()
        self.assertEqual(accentor.accent("Придержите моё ПИВО, в П+одгород"), "Придерж+ите моё П+ИВО, в П+одгород")
        self.assertEqual(seen, ["придержите моё пиво, в подгород"])

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

    def test_battle_net_friend_pinned_without_digits(self):
        # the log shows a friend as "BN:Вася": that key pins them, as does the whole BattleTag
        a = Assigner(slots(), self.path, {"BN:Вася": "creature/saurfang", "BN:Тиранда#2345": "human-female"})
        self.assertEqual(a.slot_for("BN:Вася#1234", "", "").id, "creature/saurfang")
        self.assertEqual(a.slot_for("BN:вася#99", "", "").id, "creature/saurfang")           # any case, any digits
        self.assertEqual(a.slot_for("BN:Тиранда#2345", "", "").id, "human-female")
        self.assertNotEqual(a.slot_for("BN:Тиранда#9999", "", "", now=1).id, "human-female")   # another friend
        self.assertNotEqual(a.slot_for("Вася-Степи", "Orc", "2").id, "creature/saurfang")    # a character named so

    def test_battle_net_replay_without_digits_keeps_the_voice(self):
        # /bv last from the addon's saved history: "BN:Вася", the friend heard as "BN:Вася#1234"
        a = Assigner(slots(), self.path)
        heard = a.slot_for("BN:Вася#1234", "Orc", "2", now=1).id
        a.slot_for("Орк1", "Orc", "2", now=2)
        a.slot_for("Орк2", "Orc", "2", now=3)
        self.assertEqual(a.slot_for("BN:Вася", "Orc", "2", now=4).id, heard)
        self.assertNotIn("bn:вася", a.known)                                      # no second entry for them
        self.assertEqual(a.known["bn:вася#1234"]["seen"], 4)
        # two friends of one name: the one heard last
        later = a.slot_for("BN:Вася#5678", "Orc", "2", now=5).id
        self.assertEqual(a.slot_for("BN:Вася", "Orc", "2", now=6).id, later)
        # no friend of that name heard: a voice of their own
        self.assertIsNotNone(a.slot_for("BN:Брэнн", "", "", now=7))
        self.assertIn("bn:брэнн", a.known)

    def test_battle_net_replay_before_the_whole_tag(self):
        # the friend in the history but not in assignments.json (voices reset or forgotten): the replay comes first
        a = Assigner(slots(), self.path)
        replayed = a.slot_for("BN:Друг", "Orc", "2", now=1).id
        for i in range(3):
            a.slot_for(f"Орк{i}", "Orc", "2", now=2 + i)
        live = a.slot_for("BN:Друг#1234", "Orc", "2", now=10).id
        self.assertEqual(live, replayed)                                           # the name's voice is theirs
        self.assertEqual([k for k in a.known if k.startswith("bn:")], ["bn:друг#1234"])
        self.assertEqual(a.slot_for("BN:Друг", "Orc", "2", now=11).id, live)
        self.assertEqual(a.slot_for("BN:Друг#1234", "Orc", "2", now=12).id, live)
        # and the other order: the whole tag first, then the replay
        b = Assigner(slots(), Path(self.dir.name) / "b.json")
        live = b.slot_for("BN:Друг#1234", "Orc", "2", now=1).id
        for i in range(3):
            b.slot_for(f"Орк{i}", "Orc", "2", now=2 + i)
        self.assertEqual(b.slot_for("BN:Друг", "Orc", "2", now=10).id, live)
        self.assertEqual(b.slot_for("BN:Друг#1234", "Orc", "2", now=11).id, live)
        self.assertNotIn("bn:друг", b.known)

    def test_battle_net_name_alone_kept_by_an_older_version(self):
        # a file with both entries (written before): the whole tag's voice wins, and the name's entry goes
        import json
        import time
        now = time.time()
        self.path.write_text(json.dumps({"bn:друг": {"slot": "orc-male", "seen": now - 2},
                                         "bn:друг#1234": {"slot": "orc-male#60", "seen": now - 1}}), encoding="utf-8")
        a = Assigner(slots(), self.path)
        self.assertEqual(a.slot_for("BN:Друг", "Orc", "2", now=now).id, "orc-male#60")
        self.assertEqual(a.slot_for("BN:Друг#1234", "Orc", "2", now=now + 1).id, "orc-male#60")
        self.assertNotIn("bn:друг", a.known)


    def test_battle_net_whole_tag_adopts_the_names_voice(self):
        # only the name's entry is known (a replay was the friend's first line since a reset): the whole tag takes
        # that very voice, not the next free one - a shifted copy no other speaker would pick first
        import json
        import time
        now = time.time()
        shifted = next(s.id for s in slots() if s.id.startswith("orc-male") and "^" in s.id)
        self.path.write_text(json.dumps({"bn:друг": {"slot": shifted, "seen": now - 1}}), encoding="utf-8")
        a = Assigner(slots(), self.path)
        self.assertEqual(a.slot_for("BN:Друг#1234", "Orc", "2", now=now).id, shifted)
        self.assertEqual(list(a.known), ["bn:друг#1234"])


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

    def test_battle_net_friend_by_the_tag_without_digits(self):
        # pinned as the log shows them ("BN:Вася"); a replay from the addon's history (no digits) sounds the same
        from bv.speech import Speaker, Voice
        sp = Speaker({"players": {"BN:Вася": "Voice7"}, "exclude": [], "gender_overrides": {}}, print)
        sp.all_voices = [Voice(None, f"Voice{i}", "Male", "rhvoice") for i in range(12)]
        sp.set_disabled(set())
        self.assertEqual(sp.voice_for("BN:Вася#1234", "2").description, "Voice7")
        for i in range(30):
            self.assertEqual(sp.voice_for(f"BN:Друг{i}#1234", "2"), sp.voice_for(f"BN:Друг{i}", "2"))


class SapiLoudness(unittest.TestCase):
    def test_a_line_is_made_at_full_loudness_whatever_its_volume(self):
        # the player applies the addon's volume as the line plays (the wheel); made at 50 % too it would be 25 %
        from bv.protocol import Line
        from bv.speech import Speaker
        sp = Speaker({"players": {}, "exclude": [], "gender_overrides": {}, "kind_gain_db": {}, "volume": 100}, print)
        pcm = b"".join(int(8000 * ((i % 40) - 20) / 20).to_bytes(2, "little", signed=True) for i in range(2000))
        half = Line("say", "Орк", "Orc", "2", "", "", "текст", 100, "sapi", volume=50)
        whole = Line("say", "Орк", "Orc", "2", "", "", "текст", 100, "sapi", volume=100)
        self.assertEqual(sp._loud(pcm, half), sp._loud(pcm, whole))
        self.assertEqual(sp._loud(pcm, half), sp._even(pcm, "say", 1.0))


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

    def test_a_phrase_s_ending_in_lower_case(self):
        # a player's «*» phrase takes the ending as typed - in lower case, as the replacement is
        d = self.book()
        d.receive({"id": "p1", "part": "1", "of": "1"}, "мертвые копи*=мёртвые к+опи*")
        self.assertEqual(d.apply_words("в МЕРТВЫЕ КОПИЯХ"), "в мёртвые к+опиях")

    def test_rl(self):
        # «РЛ» letter by letter, «эр-эл»: the raid leader or the Ruins of Lordaeron, the words around cannot tell
        from bv.morph import Inflector
        d, inf = self.book(), Inflector(print)

        def read(text):
            return inf.apply(d.apply(inf.apply(d.apply_words(text)), mark=True))
        for text, said in {"встречаемся в РЛ": "встречаемся в эр-+эл", "у РЛ спроси": "у эр-+эл спроси",
                           "к РЛ обратись": "к эр-+эл обратись", "из РЛ": "из эр-+эл",    # as written: not declined
                           "РЛ кинул инвайт": "эр-+эл кинул инвайт", "РЛ есть в гильдии?": "эр-+эл есть в гильдии?",
                           "РЛ есть: танк, хил": "эр-+эл есть: т+анк, х+ил", "нужен РЛ на МК": "нужен эр-+эл на МК",
                           "пишите РЛу": "пишите эр-+элу", "с рлом договорились": "с эр-+элом договорились",
                           "в РЛе": "в эр-+эле", "о рлах": "о эр-+элах", "РЛ-у": "эр-+элу", "РЛ.": "эр-+эл.",
                           "с рлами": "с эр-+элами", "рлы": "эр-+элы",
                           "орл": "орл"}.items():
            self.assertEqual(read(text), said, text)

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

    def test_renamed_rl_rules_keep_the_players_own(self):
        # «РЛ»'s rules keep 0.4.0's keys: a player's own line for one replaces it in place; «бр» became two rules
        # (D.RENAMED): who changed or deleted the word gets neither
        for own, text, said in (("~\\bрл\\b=рейд-лидер", "РЛ кинул инвайт", "рейд-лидер кинул инвайт"),
                                ("~\\bрл-?(а|у|ом|ы|ов|ам|ами|е)\\b=лидер\\1", "пишите РЛу", "пишите лидеру"),
                                ("~\\b(\\d+)\\s*рл\\b=\\1 [лидер|лидера|лидеров]", "нужно 2 рл", "нужно 2 лидера"),
                                ("~\\bрл\\b=рейд-лидер", "пишите РЛу", "пишите эр-+элу"),
                                ("~\\bрл-?(а|у|ом|ы|ов|ам|ами|е)\\b=лидер\\1", "рл афк", "эр-+эл отошёл"),
                                ("~\\bрл\\b=рейд-лидер", "нужно 2 рл", "нужно 2 эр-+эла"),
                                ("!бр=боевое воскрешение", "есть 2 бр", "есть 2 бр"),
                                ("!бр=боевое воскрешение", "бр на кд", "бр на кулд+аун"),
                                ("!~\\bрл\\b", "РЛ кинул инвайт", "РЛ кинул инвайт"),
                                ("бр=боевое воскрешение", "дай бр", "дай боевое воскрешение")):
            d = self.book()
            d.receive({"id": "own", "part": "1", "of": "1"}, own)
            self.assertEqual(d.apply(d.apply_words(text)).replace("\x02", "").replace("\x03", ""), said, own)

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
        # the default's «рл» entries agree with the count: «два эр-эла», not «второй эр-эла»
        self.check({"2 рла": "два эр-+эла", "5 рлов": "пять эр-+элов", "2 топ-гильдии": "две топ-гильдии"})

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
            # a price in the middle of a phrase is still silver
            "5 с за штуку": "пять серебра за штуку", "отдам за 50 с или 1 г": "отдам за пятьдесят серебра или один г",
            "цена 5 с каждый": "цена пять серебра каждый", "5 с и 3 м": "пять серебра и три м",
            "5 с 20 м": "пять серебра двадцать меди", "по 50 с за шт": "по пятьдесят серебра за шт",
            # ... but not before a word that only starts like one, nor «и без»
            "дуэль 1 на 1 с каждым": "дуэль один на один с каждым", "нас 5 с и без хила": "нас пять с и без хила",
            "группа 4 с или без танка": "группа четыре с или без танка", "нужен 1 с штанами": "нужен один с штанами",
        })

    def test_level_in_every_case_and_niche(self):
        self.check({"мне не хватает лвла": "мне не хватает уровня", "до 60 лвла": "до шестидесятого уровня",
                    "с лвлом": "с уровнем", "без лвлов": "без уровней", "на каком ты лвле": "на каком ты уровне",
                    "апнул лвл": "апнул уровень", "ниче страшного": "ничё страшного"})

    def test_skachki_by_meaning_and_not_declined(self):
        self.check({"скачки патча долгие": "ск+ачки патча долгие", "после скачки клиента": "после ск+ачки клиента",
                    "у меня скачки фпс": "у меня скачк+и фпс", "из-за скачки пинга": "из-за скачк+и пинга",
                    "были скачки по фпс": "были скачк+и по фпс", "скачки в пинге": "скачк+и в пинге",
                    "скачки урона": "скачк+и урона", "скачки и лаги": "скачк+и и лаги", "скачки хп": "скачк+и здоровье",
                    "скачки в рейд": "ск+ачки в рейд", "скачки по пингу": "скачк+и по пингу",
                    "скачки по хп": "скачк+и по здоровью", "скачки по урону": "скачк+и по урону",
                    "скачки по патчу": "ск+ачки по патчу"})

    def test_roga_is_a_rogue(self):
        self.check({"нужна рога в рейд": "нужна р+ога в рейд", "для роги": "для р+оги", "с рогой": "с р+огой",
                    "рогу дали": "р+огу дали", "две роги": "две р+оги", "рогами": "р+огами",
                    "нет рогов в рейде": "нет р+огов в рейде", "рогатый": "рогатый"})

    def test_btw_in_russian_letters(self):
        self.check({"бтв я завтра не смогу": "кстати я завтра не смогу", "Бтв": "кстати", "бтвх": "бтвх"})

    def test_skraftit_and_vendor_stress(self):
        self.check({"скрафтить": "скр+афтить", "скрафтил": "скр+афтил",
                    "у вендора": "у в+ендора", "вендоров": "в+ендоров", "крафт": "крафт"})

    def test_burger_stress(self):
        self.check({"бургеры": "б+ургеры", "бургер": "б+ургер", "без бургеров": "без б+ургеров"})

    def test_summon_stress(self):
        self.check({"суманем": "суман+ём", "щас суманем": "щас суман+ём", "суманешь": "суман+ёшь", "суманет": "суман+ёт",
                    "суманете": "суман+ёте", "суманём": "суман+ём", "щас суману": "щас суман+у",
                    "суманут": "суман+ут", "сумануть": "суман+уть", "суманул": "суман+ул", "суманули": "суман+ули",
                    "суманула": "суман+ула"})

    def test_the_addon_and_its_sites(self):
        self.check({"barrens voice на curse forge": "Б+эрренс В+ойс на К+ёрс Ф+ордж", "есть на CurseForge": "есть на К+ёрс Ф+ордж",
                    "и на wago": "и на В+аго", "Barrens Voice": "Б+эрренс В+ойс", "barrensvoice": "Б+эрренс В+ойс",
                    # as written after any preposition: declining changed the first word only («с К+ёрсом Ф+ордж»)
                    "скачай с curseforge": "скачай с К+ёрс Ф+ордж", "из curse forge": "из К+ёрс Ф+ордж",
                    "о barrens voice": "о Б+эрренс В+ойс", "для barrens voice": "для Б+эрренс В+ойс",
                    "к barrens voice": "к Б+эрренс В+ойс", "под barrensvoice": "под Б+эрренс В+ойс",
                    "с wago": "с В+аго", "на wago.io": "на В+аго"})

    def test_global_chat(self):
        self.check({"пиши в глобал": "пиш+и в гл+обал", "из глобала": "из гл+обала", "в глобале тихо": "в гл+обале тихо",
                    "в глобалах": "в гл+обалах", "глобальный": "глобальный", "глобалы": "гл+обалы",
                    "нет глобалов": "нет гл+обалов", "по глобалам": "по гл+обалам", "с глобалами": "с гл+обалами"})

    def test_leveling_verb(self):
        self.check({"он качается": "он кач+ается", "где качаться": "где кач+аться", "мы качаемся": "мы кач+аемся",
                    "качался долго": "кач+ался долго", "качалась": "кач+алась", "кача нет": "к+ача нет",
                    "качалось": "кач+алось"})

    def test_dimons(self):
        self.check({"дарова": "дар+ова", "дарова всем!": "дар+ова всем!", "о, дарова!": "о, дар+ова!",
                    "о дарова": "о дар+ова", "ну дарова": "ну дар+ова", "здарова": "здар+ова",
                    "о, здарова!": "о, здар+ова!", "даров": "дар+ов", "дарово всем": "дар+ово всем",
                    "о, даров!": "о, дар+ов!", "о, дарово!": "о, дар+ово!",
                    "здаров": "здар+ов", "здарово всем": "здар+ово всем", "дароу": "дар+оу", "о, здароу!": "о, здар+оу!",
                    "о, здаров!": "о, здар+ов!", "у здаров": "у здар+ов", "о, здарово!": "о, здар+ово!",
                    "я новичек": "я новичёк", "о, новичек": "о, новичёк", "новичка": "новичка"})
        self.check({"опять димоны": "опять д+имоны", "против димонов": "против д+имонов", "димон, привет": "димон, привет",
                    "о димонах": "о д+имонах", "при димонах": "при д+имонах", "с димонами": "с д+имонами"})

    def test_khuevo(self):
        self.check({"хуево": "хуёво", "все хуево": "все хуёво", "Хуево": "хуёво", "хуевый танк": "хуёвый т+анк",
                    "хуевая игра": "хуёвая игра", "хуевенько": "хуёвенько", "до хуев": "до хуёв", "хуёво": "хуёво",
                    "хуета": "хуета", "охуевать": "охуевать"})
        # a word in capitals taken by a stem: its ending in lower case too (was «хуёвО», «б+ургерЫ»)
        self.check({"ХУЕВО": "хуёво", "БУРГЕРЫ взял": "б+ургеры взял", "ВЕНДОРУ": "в+ендору"})
        # «хуева туча» (много) - х+уева, not «хуёва»; «хуевато» - хуев+ато
        self.check({"хуева туча мобов": "х+уева т+уча мобов", "из хуевой тучи": "из х+уевой т+учи",
                    "с хуевой тучей": "с х+уевой т+учей", "в хуевой туче": "в х+уевой т+уче",
                    "хуеву тучу": "х+уеву т+учу", "хуевато": "хуев+ато", "хуевая туча": "хуёвая туча"})

    def test_latin_c_after_a_number(self):
        # «50c» typed in the English layout: silver, as «50с» - it sounded «пятьдесят си»
        self.check({"Такси до Подгорода 50c": "Такси до П+одгорода пятьдесят серебра", "50 c": "пятьдесят серебра",
                    "2g50c": "два золотых пятьдесят серебра", "по 50c за порт": "по пятьдесят серебра за порт",
                    "abc": "abc", "c 5": "c пять", "5 c хилом": "пять c хилом", "50C": "пятьдесят серебра",
                    "50 c за порт": "пятьдесят серебра за порт", "50 c шт": "пятьдесят серебра шт",
                    "50 c каждый": "пятьдесят серебра каждый", "50 c, торг": "пятьдесят серебра, торг",
                    "50 c или 1 g": "пятьдесят серебра или один золотой",
                    # seconds, as with the Cyrillic «с»: after a cooldown or a cast, after «через», before «кд»
                    "кд 5c": "кулд+аун пять секунд", "каст 2c": "каст две секунды", "откат 30c": "откат тридцать секунд",
                    "через 5c": "через пять секунд", "через 5 c": "через пять секунд", "5c кд": "пять секунд кулд+аун",
                    # copper after a silver amount
                    "2g 50s 30c": "два золотых пятьдесят серебра тридцать меди", "5s 20c": "пять серебра двадцать меди",
                    "50s 30 c": "пятьдесят серебра тридцать меди", "50s, 30c": "пятьдесят серебра тридцать меди",
                    "50 s  30c": "пятьдесят серебра тридцать меди", "50с 30м": "пятьдесят серебра тридцать меди",
                    "2з 50с 30м": "два золотых пятьдесят серебра тридцать меди", "через 5с 10c": "через пять секунд десять серебра",
                    "yes 30c": "yes тридцать серебра", "кд 5 c": "кулд+аун пять секунд", "5 c кд": "пять секунд кулд+аун",
                    "через 5 c половиной": "через пять c половиной", "50 c или без": "пятьдесят c или без",
                    "2g50s 30c": "два золотых пятьдесят серебра тридцать меди",
                    "2г50с 30м": "два золотых пятьдесят серебра тридцать меди", "кд 5с 30м": "кулд+аун пять секунд тридцать м",
                    "2 г 50 с 30 м": "два золотых пятьдесят серебра тридцать меди"})

    def test_nzch_stressed_on_ne_and_np(self):
        # «не́ за что»: without the mark RUAccent left «не» unstressed and stressed «что» - heard as «ни за что́»
        # one word, as it is said: RUAccent leaves a word with a mark alone, so «что» gets no stress of its own
        self.check({"нзч": "н+езачто", "спасибо, нзч": "спасибо, н+езачто", "не за что": "н+езачто",
                    "Не за что!": "н+езачто!", "да не за что": "да н+езачто", "незачто": "н+езачто",
                    "не, за что?": "не, за что?", "Не. За что?": "Не. За что?", "не за что-то": "не за что-то",
                    "не за что зацепиться": "н+езачто зацепиться", "не за что то": "не за что то",
                    "бан не за что нибудь": "бан не за что нибудь", "не  за что": "н+езачто", "не за чтоб": "не за чтоб",
                    "не за что тогда": "н+езачто тогда",
                    "np": "без проблем", "спасибо, np": "спасибо, без проблем", "нп": "без проблем"})

    def test_use(self):
        self.check({"усе": "всё", "ну усе, я спать": "ну всё, я спать", "за усе спасибо": "за всё спасибо",
                    "Усе пропало": "всё пропало", "усек": "усёк", "усеять": "усеять"})

    def test_tier(self):
        # an armour set's tier: «тэ один», not «тодин»; a word on its own only
        # spelt in the rule: a digit left would agree with the next word («т2 сет» - «тэ второй сет»)
        self.check({"т1": "тэ один", "нужен т1 сет": "нужен тэ один сет", "т2 и т3": "тэ два и тэ три",
                    "Т1": "тэ один", "t1": "тэ один", "т10": "тэ десять", "5т1": "пять тодин", "кт1": "ктодин",
                    "т2 сет": "тэ два сет", "т3 сет": "тэ три сет", "т2 шапка": "тэ два шапка",
                    "т2 перчатки": "тэ два перчатки", "т2 ноги": "тэ два ноги", "т1 шапка": "тэ один шапка",
                    "т1 вещи": "тэ один вещи", "т7 сет": "тэ семь сет", "в т2": "в тэ два",
                    "т100": "тсто", "т1сет": "тодин сет", "lf t2": "ищу тэ два", "т0": "тэ ноль", "т4": "тэ четыре",
                    "т5": "тэ пять", "т6": "тэ шесть", "т8": "тэ восемь", "т9": "тэ девять", "т11": "тэ одиннадцать",
                    "т21 сет": "тэ двадцать один сет", "т12": "тэ двенадцать", "т13": "тэ тринадцать",
                    "т14": "тэ четырнадцать", "т15": "тэ пятнадцать", "т16": "тэ шестнадцать", "т17": "тэ семнадцать",
                    "т18": "тэ восемнадцать", "т19": "тэ девятнадцать", "т20": "тэ двадцать"})

    def test_chekn(self):
        self.check({"чекну": "ч+екну", "чекни почту": "ч+екни почту", "Чекнул": "ч+екнул", "чекнуть": "ч+екнуть",
                    "ЧЕКНЕМ": "ч+екнем", "чек": "чек", "чекать": "ч+екать",
                    "Чекать почту": "ч+екать почту", "чеканка": "чеканка"})

    def test_places_ruaccent_misreads(self):
        self.check({"Степи подвергается нападению!": "Ст+епи подвергается нападению!",
                    "Леса Ночной Песни подвергается нападению!": "Лес+а Ночн+ой П+есни подвергается нападению!",
                    "в степи никого": "в Ст+епи никого", "кто идёт в Степи?": "кто идёт в Ст+епи?",
                    "го Степи": "го Ст+епи", "из степи": "из Ст+епи", "Пылающие степи": "Пылающие Ст+епи",
                    "в степь": "в степь", "в степях": "в степях", "го в леса ночной песни": "го в Лес+а Ночн+ой П+есни",
                    "в лесах": "в лесах", "го Глубины Черной горы": "го Глуб+ины Чёрной горы",
                    "на Келебраса Проклятого": "на Келебраса Пр+оклятого", "Келебрас Проклятый": "Келебрас Пр+оклятый",
                    "Фантом Адского Крика": "Фантом Адского Крика", "Змеиные Кольца": "Змеиные Кольца",
                    "го на Буру": "го на Б+уру", "Акульи воды": "Акульи в+оды", "го Острова Эха": "го Остров+а Эха",
                    "Острова Эха подвергается нападению!": "Остров+а Эха подвергается нападению!",
                    "Поля Великанов подвергается нападению!": "Пол+я Великанов подвергается нападению!",
                    "лфг Острова Черного Копья": "ищу группу Остров+а Чёрного Копь+я",
                    "Тролли из племени Пронзающего Копья": "Тролли из племени Пронзающего Копь+я",
                    "го Земли Ящеров": "го З+емли Ящеров", "Горы Штормграда": "Г+оры Штормграда",
                    "в Грот Слез": "в Грот Слёз", "Слезы Далсона": "Слёзы Далсона", "у Озера Слез": "у Озера Слёз",
                    "Озеро Слез": "Озеро Слёз", "у Слез Далсона": "у Слёз Далсона", "слез с коня": "слез с коня",
                    "го в Земли Иглогривых": "го в З+емли Иглогривых", "у Пронзающего Копья": "у Пронзающего Копь+я",
                    "с острова": "с острова", "буруны": "буруны", "армия Плети кто?": "армия Пл+ети кто?",
                    "у Плети нет шансов": "у Пл+ети нет шансов", "плетись": "плетись", "в топик": "в топик",
                    "из Грота Слез": "из Грота Слёз", "в Гроте Слез": "в Гроте Слёз", "на Озере Слез": "на Озере Слёз",
                    "к Гроту Слез": "к Гроту Слёз", "за Озером Слез": "за Озером Слёз",
                    "за Гротом Слез": "за Гротом Слёз", "к Озеру Слез": "к Озеру Слёз",
                    "идем в топи": "идём в Т+опи", "кто в Топи?": "кто в Т+опи?", "топи печь": "топи печь",
                    "фарм камней Плети в Чумных землях": "ф+арм камней Пл+ети в Чумных землях",
                    "из Глубин Черной горы": "из Глубин Чёрной горы", "Земли Хаккари": "З+емли Хаккари", "го брд": "го Глуб+ины Чёрной горы",
                    "LFM BRD": "ищем ещё Глуб+ины Чёрной горы", "из брд": "из Глуб+ин Чёрной горы"})

    def test_moroka(self):
        self.check({"ну и морока": "ну и мор+ока", "Мороки много": "мор+оки много", "с этой морокой": "с этой мор+окой",
                    "морок": "морок", "без мороки": "без мор+оки", "к мороке": "к мор+оке", "про мороку": "про мор+оку",
                    "с морокой": "с мор+окой", "вечно морока то танка нет": "вечно мор+ока то танка нет"})

    def test_to_est(self):
        self.check({"т.е. бесплатно": "то есть бесплатно", "т. е. бесплатно": "то есть бесплатно", "т.е": "то есть",
                    "т.к. бесплатно": "т.к. бесплатно", "мост.ек": "мост.ек",
                    "т.е.я пас": "то есть я пас", "т.е.бесплатно": "то есть бесплатно", "т.е.рл": "то есть эр-+эл",
                    "т.е.кк": "то есть окей", "т.е.5к": "то есть пять тысяч", "те кто": "те кто",
                    "пакет.е": "пакет.е", "т.еще": "т.ещё", "т.е.60лвл": "то есть шестидесятый уровень",
                    "т.е.50%": "то есть пятьдесят процентов", "т.е.imho": "то есть +имхо", "т.е.barrens": "то есть barrens", "т.е.+1": "то есть +один"})

    def test_yomayo(self):
        self.check({"емае": "ёма+ё", "Ёмае, опять": "ёма+ё, опять", "ЕМАЕ": "ёма+ё", "о емае, опять": "о ёма+ё, опять",
                    "от емае": "от ёма+ё"})

    def test_rostov_on_don(self):
        self.check({"еду в Ростов-на-Дону": "еду в Ростов-на-Дон+у", "ростов-на-дону": "Ростов-на-Дон+у",
                    "из Ростова-на-Дону": "из Ростова-на-Дон+у", "в Ростове-на-Дону": "в Ростове-на-Дон+у",
                    "к Ростову-на-Дону": "к Ростову-на-Дон+у"})

    def test_stack_verb_stress(self):
        self.check({"не стакается": "не ст+акается", "стакаются": "ст+акаются", "стакаться": "ст+акаться",
                    "стакалось": "ст+акалось", "стакалась": "ст+акалась", "стакались": "ст+акались",
                    "стакаем": "ст+акаем", "стакаю": "ст+акаю", "застакаются": "заст+акаются",
                    "стакался": "ст+акался", "стакает": "ст+акает", "стакать": "ст+акать", "застакается": "заст+акается",
                    "стакала": "ст+акала", "стакаете": "ст+акаете", "застакалось": "заст+акалось",
                    "застакался": "заст+акался", "стакан": "стакан"})

    def test_buff_verb_stress(self):
        self.check({"он бафает": "он б+афает", "бафать": "б+афать", "я бафаю": "я б+афаю", "баффает": "б+аффает",
                    "баф": "б+аф", "бафни": "б+афни", "бафнул": "б+афнул", "бафы": "б+афы", "нет бафов": "нет б+афов",
                    "баффы": "б+аффы", "дебафы": "деб+афы", "дебаф": "деб+аф", "дебаффы": "деб+аффы",
                    "бафомет": "бафом+ет", "бафомета": "бафом+ета", "ребаф": "реб+аф", "ребафни": "реб+афни",
                    "нужен ребафф": "нужен реб+афф"})

    def test_gnomeregan_stress(self):
        self.check({"гномреган": "гномрег+ан", "в гномрегане": "в гномрег+ане", "из гномрегана": "из гномрег+ана"})

    def test_forever_stress(self):
        self.check({"форевер": "фор+евер", "на форевере": "на фор+евере", "для форевера": "для фор+евера",
                    "с форевером": "с фор+евером"})

    def test_sm_by_case(self):
        # «см» in lower case after a number is centimetres, bare it is left alone («смотри», the dungeon typed
        # small), the dungeon «СМ» (Scarlet Monastery) in capitals only
        self.check({"всего 5 см": "всего пять сантиметров", "2см": "два сантиметра", "на 1 см": "на один сантиметр",
                    "го в СМ": "го в Монастырь Алого ордена", "из СМ": "из Монастыря Алого ордена",
                    "ещё см": "ещё см", "см. выше": "см. выше", "го в см": "го в см", "смайл": "смайл"})

    def test_rmt_by_letters(self):
        self.check({"это рмт": "это Эр Эм Тэ", "за RMT бан": "за Эр Эм Тэ бан", "РМТ": "Эр Эм Тэ"})

    def test_v_dushe_is_the_soul(self):
        self.check({"я в душе не знаю": "я в душ+е не знаю", "Добрый в душе": "Добрый в душ+е", "душевный": "душевный"})

    def test_np_by_case(self):
        # «нп» in lower case (or «Нп» starting a phrase) is «без проблем», the dungeon only in capitals
        self.check({"спасибо! нп": "спасибо! без проблем", "Нп, обращайся": "без проблем, обращайся",
                    "го в НП": "го в Непроглядную пучину", "из НП": "из Непроглядной пучины", "нпс": "нпс"})

    def test_keep_case_mark(self):
        # «=!»: a replacement as written, never declined after a preposition - a word, a regex; without it: declined
        from bv.__main__ import speech_text
        from bv.dictionary import Dictionary, parse
        book = Dictionary({}, lambda *a: None, self.ADDON)
        book.exact = {"хрусталь": "перекрёсток", "кристалл": "!перекрёсток"}
        book.stems, book.phrases = [], {}
        book.rules = parse("~\\bальфа\\b=перекрёсток\n~\\bбета\\b=!перекрёсток", print)
        said = {t: speech_text(t, book, self.inflector, True) for t in ("у хрусталь", "у кристалл", "у альфа", "у бета")}
        self.assertEqual(said, {"у хрусталь": "у перекрёстка", "у кристалл": "у перекрёсток",
                                "у альфа": "у перекрёстка", "у бета": "у перекрёсток"})
        self.assertEqual(speech_text("у бета", book, self.inflector, False), "у перекрёсток")   # declension off: no mark left
        # with a number's forms: the preposition before the number still asks the plural (D12N1: «для второго танка»)
        from bv.text import numbers_to_words
        book.rules = parse("~\\b(\\d+)\\s*тнк\\b=!\\1 [танк|танка|танков]", print)
        self.assertEqual(numbers_to_words(speech_text("для 2 тнк", book, self.inflector, True)), "для двух танков")

    def test_dolboyob_with_yo_in_every_form(self):
        self.check({"эти долбаебами": "эти долбаёбами", "с долбоебами": "с долбоёбами", "он долбоеб": "он долбоёб",
                    "у долбоеба": "у долбоёба", "долбаебы": "долбаёбы", "долбить": "долбить"})

    def test_temp_is_hard(self):
        said = self.say("держи темп, сбавь темпа, температура")
        self.assertIn("тэмп", said)
        self.assertNotIn("тэмпература", said.replace("+", ""))
        self.assertIn("тэмпа", said.replace("+", ""))

    def test_a_heart_is_a_smiley(self):
        # «<3» at the end of a line, where it is put, is a pause like the other smileys (it was «<три»)
        for line in ("люблю тебя <3", "спасибо <3 <3", "<333", "спасибо </3", "<3", "люблю тебя <3!"):
            self.assertNotIn("три", self.say(line), line)
        # inside a line it is a number: «меньше трёх»
        for line, number in (("кд <3 сек", "три"), ("<3 минут до ресета", "три"), ("хп <3к осталось", "три тысячи"),
                             ("цена <3г за штуку", "три золот"), ("<333 супер", "триста")):
            self.assertIn(number, self.say(line), line)
        self.assertIn("тридцать", self.say("х<30 урон"))
        self.assertIn("тридцать третьем", self.say("о 33 лвл"))        # the dictionary's own «<33>» is no heart

    def test_spek_is_no_spyok(self):
        # the «ё» dictionary made the talents' «спек» into the verb «спёк»; a stressed entry keeps it
        self.check({"какой у тебя спек": "какой у тебя сп+ек", "сменил спек": "сменил сп+ек", "в спеке": "в спеке"})

    def test_seconds_after_a_cooldown_and_no_seconds_before_a_half(self):
        self.check({
            "кд 30 с": "кулд+аун тридцать секунд", "каст 2 с": "каст две секунды", "откат 10 с": "откат десять секунд",
            "через 2 с половиной часа": "через два с половиной часа",
            "через 5 с половиной минут": "через пять с половиной минут",
            "через 5с пул": "через пять секунд п+ул", "через 5 сек": "через пять секунд",
            "кд 30с": "кулд+аун тридцать секунд", "кд 30 сек пул": "кулд+аун тридцать секунд п+ул",
            # a spaced «с» going on is the preposition
            "кастую 5 с тобой": "кастую пять с тобой", "откат 10 с момента": "откат десять с момента",
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

    def test_rl_after_a_number(self):
        # «рл» after a number agrees with it
        self.check({"нужен 1 рл": "нужен один эр-+эл", "нужно 2 рл": "нужно два эр-+эла",
                    "нужно 5 рл": "нужно пять эр-+элов", "у 2 рл": "у двух эр-+элов", "21 рл": "двадцать один эр-+эл",
                    "идём в рл": "идём в эр-+эл", "2рл": "два эр-+эла",
                    # an ending of the player's own after a hyphen: the plain rule's, not «пять эр-эла-ам»
                    "5 РЛ-ам": "пять эр-+элам", "2 РЛ-у": "два эр-+элу", "3 РЛ-ом": "три эр-+элом"})

    def test_onyxia(self):
        self.check({"Ониксия": "он+иксия", "идём на Ониксию": "идём на он+иксию", "у Ониксии": "у он+иксии",
                    "с Ониксией": "с он+иксией", "оня в 8": "Он+иксия в восемь", "онька": "Он+иксия",
                    "идём на оню": "идём на Он+иксию", "на оньку": "на Он+иксию", "о, оня!": "о, Он+иксия!", "о, онька!": "о, Он+иксия!",
                    "я на оне": "я на Он+иксии", "кд по оне": "кулд+аун по Он+иксии",
                    "они идут": "они идут", "без они": "без они", "ониксовый": "ониксовый"})

    def test_br_after_a_number(self):
        self.check({"есть 2 бр": "есть два бэ+эра", "нужен 1 бр": "нужен один бэ+эр", "5 бр": "пять бэ+эров",
                    "бр, холодно": "бэ+эр, холодно", "без бр": "без бэ+эр", "кинь БР на хила": "кинь бэ+эр на хила",
                    "у 2 бр": "у двух бэ+эров", "бр-р": "бр-р"})


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
        addon = dict(re.findall(r'(\w+) = \{ "[^"]+", "([^"]+)"(?:, "[^"]+")? \}', block))
        self.assertEqual(addon, LINKS)
        # a community's invite code (the game opens it itself) is the code of its web address
        for key, url, ticket in re.findall(r'(\w+) = \{ "[^"]+", "([^"]+)", "([^"]+)" \}', block):
            self.assertEqual(url.rsplit("/", 1)[1], ticket, key)


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

    def test_the_default_s_stress_is_before_a_vowel(self):
        # a «+» before a consonant reaches the Windows voices as a plain «+» (apply_stress takes it before a vowel)
        from bv.dictionary import default_text
        from bv.text import apply_stress
        lua = (Path(__file__).resolve().parents[2] / "addon" / "BarrensVoice" / "Dictionary.lua").read_text(encoding="utf-8")
        for line in default_text(lua).splitlines():
            if not line.strip() or line.startswith("#") or "=" not in line:
                continue
            value = line.rsplit("=", 1)[1] if not line.startswith("~") else line.split(")=", 1)[-1].split("\\b=", 1)[-1]
            value = value.lstrip("!")
            self.assertNotIn("+", apply_stress(value.split("=")[-1], "strip").replace("\\+", ""), line)

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
        player = Player(8)                                  # not started: no thread, no stream
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


def fake_out(fail_first=False):
    """(the lines played - each by its last byte, a fake output): the real one (StreamOut) needs a sound device."""
    import threading
    played, lock, calls = [], threading.Lock(), []

    class Out:
        def play(self, data, level, stopped, length):
            calls.append(data)
            if fail_first and len(calls) == 1:
                raise RuntimeError("Failed to play sound")
            with lock:
                played.append(data[-1:])                    # a line's last byte names it
            stopped.wait(length)
    return played, Out()


def marked_line(mark: bytes, secs: float) -> bytes:
    """A silent line `secs` long whose last byte is `mark`."""
    from bv.audio import wav
    return wav(b"\0\0" * int(8000 * secs), 8000)[:-1] + mark


class PauseForCatQuest(unittest.TestCase):
    """While CatQuest speaks the player holds the lines; the line it cut is played again from its
    start, then the queue (a fake output: the real one needs a sound device)."""

    def test_cut_line_again_then_queue(self):
        import tempfile
        import time
        played, fake = fake_out()
        from bv.audio import Player
        with tempfile.TemporaryDirectory() as d:
            p = Player(8, out=fake)
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
        played, fake = fake_out()
        logged = []
        with tempfile.TemporaryDirectory() as d, mock.patch.object(audio, "PAUSE_MAX", 0.2):
            p = audio.Player(8, log=logged.append, out=fake)
            p.start()
            p.pause()                                    # CatQuest's "resume" never comes
            p.play(marked_line(b"A", 0.1))
            time.sleep(0.2)
            self.assertEqual(played, [])
            time.sleep(1.0)                              # PAUSE_MAX later (checked every 0.5 s): on its own
            self.assertEqual(played, [b"A"])
            self.assertTrue(any(m.startswith("пауза для CatQuest дольше") for m in logged), logged)


class LiveVolume(unittest.TestCase):
    """The mouse wheel's volume reaches the line already playing: the stream reads the volume asked for every block, both
    ways, 0..2 of the line (over full the peaks eased); a line is made at full loudness."""

    class FakeSD:
        """sounddevice's part StreamOut uses: a stream whose blocks run on a thread, as PortAudio's callback does."""
        class CallbackStop(Exception):
            pass

        def __init__(self, blocks_wait=0.0, first_wait=0.0):
            self.blocks, self.aborted, self.wait, self.first_wait = [], False, blocks_wait, first_wait

        def OutputStream(self, samplerate, channels, dtype, blocksize, callback, finished_callback, device=None):
            import numpy as np
            import threading
            sd = self

            class Stream:
                def start(self):
                    def run():
                        time.sleep(sd.first_wait)            # PortAudio: the first block a buffer after the start
                        while not sd.aborted:
                            out = np.zeros((blocksize, channels), dtype="float32")
                            try:
                                callback(out, blocksize, None, None)
                            except sd.CallbackStop:
                                sd.blocks.append(out[:, 0].copy())
                                break
                            sd.blocks.append(out[:, 0].copy())
                            time.sleep(sd.wait)
                        finished_callback()
                    import time
                    threading.Thread(target=run, daemon=True).start()

                def abort(self):
                    sd.aborted = True

                def stop(self):
                    sd.aborted = True

                def close(self):
                    pass
            return Stream()

    def test_the_line_playing_follows_both_ways(self):
        import threading
        import numpy as np
        from bv import audio
        pcm = (np.full(8000, 0.25) * 32767).astype("<i2").tobytes()      # a steady 0.25 for a second at 8 kHz
        data = audio.wav(pcm, 8000)
        sd = self.FakeSD(blocks_wait=0.001)
        gain = {"v": 1.0}
        changed = threading.Event()

        def level():
            if len(sd.blocks) == 3 and not changed.is_set():   # the wheel, while the line plays
                gain["v"] = 2.0
                changed.set()
            return gain["v"]
        audio.StreamOut(sd).play(data, level, threading.Event(), audio.seconds(data))
        first, later = sd.blocks[0], sd.blocks[4]
        self.assertAlmostEqual(float(first[0]), 0.25, places=3)          # as made
        self.assertAlmostEqual(float(later[0]), 0.5, places=3)           # twice as loud, at once
        sd2 = self.FakeSD()
        audio.StreamOut(sd2).play(data, lambda: 8.0, threading.Event(), 1.0)
        self.assertLess(float(np.max(np.abs(sd2.blocks[0]))), 1.0)     # over full: eased, never reaching 1
        sd3 = self.FakeSD()
        audio.StreamOut(sd3).play(data, lambda: 0.0, threading.Event(), 1.0)
        self.assertEqual(float(np.max(np.abs(sd3.blocks[0]))), 0.0)      # down to silence

    def test_a_long_line_is_no_stall(self):
        # a line longer than STALL plays through on one stream: the blocks keep the beat
        import threading
        import numpy as np
        from unittest import mock
        from bv import audio
        data = audio.wav((np.ones(4000) * 1000).astype("<i2").tobytes(), 8000)      # half a second
        sd = self.FakeSD(blocks_wait=0.05)                                          # 4 blocks, 0.2 s
        sd.opened = 0
        real = sd.OutputStream

        def counting(**kw):
            sd.opened += 1
            return real(**kw)
        sd.OutputStream = counting
        with mock.patch.object(audio.StreamOut, "STALL", 0.15):
            audio.StreamOut(sd).play(data, lambda: 1.0, threading.Event(), 0.5)
        self.assertEqual(sd.opened, 1)

    def test_a_slow_start_is_no_stall(self):
        # opening and starting the stream take longer than STALL (a slow device): the line still plays, once
        import threading
        import numpy as np
        from unittest import mock
        from bv import audio
        data = audio.wav((np.ones(800) * 1000).astype("<i2").tobytes(), 8000)
        sd = self.FakeSD(first_wait=0.05)
        real = sd.OutputStream
        opened = []

        def slow(**kw):
            opened.append(1)
            stream = real(**kw)
            start = stream.start

            def slow_start():
                time.sleep(0.3)
                start()
            stream.start = slow_start
            return stream
        import time
        sd.OutputStream = slow
        with mock.patch.object(audio.StreamOut, "STALL", 0.2):
            audio.StreamOut(sd).play(data, lambda: 1.0, threading.Event(), 0.1)
        self.assertEqual(len(opened), 1)
        self.assertTrue(sd.blocks)

    def test_a_stream_ending_early_goes_on(self):
        # the stream finished before the line's end (the device dropped it): the list read again, on from there
        import threading
        import numpy as np
        from bv import audio
        data = audio.wav((np.arange(8000) % 100).astype("<i2").tobytes(), 8000)
        sd = self.FakeSD()
        real = sd.OutputStream
        opened = []

        def early(**kw):
            opened.append(1)
            if len(opened) == 1:                     # two blocks, then «finished»
                cb, fin = kw["callback"], kw["finished_callback"]
                calls = {"n": 0}

                def two(out, frames, t, st):
                    calls["n"] += 1
                    if calls["n"] > 2:
                        raise sd.CallbackStop
                    cb(out, frames, t, st)
                kw = dict(kw, callback=two)
            return real(**kw)
        sd.OutputStream = early
        sd._terminate = lambda: None
        sd._initialize = lambda: setattr(sd, "aborted", False)
        audio.StreamOut(sd).play(data, lambda: 1.0, threading.Event(), 1.0)
        self.assertEqual(len(opened), 2)

    def test_a_failed_start_of_portaudio_is_said_and_recovers(self):
        # PortAudio does not start again once (reopen): said as StreamBroken; the next line starts it afresh, though
        # stopping a PortAudio not started raises
        import threading
        from bv import audio

        class SD(self.FakeSD):
            def __init__(self):
                super().__init__()
                self.up, self.fail_start = True, 1

            def OutputStream(self, **kw):
                if not self.up:
                    raise RuntimeError("PortAudio not initialized")
                if self.fail_start:                      # the device gone: this stream fails
                    raise RuntimeError("device unavailable")
                return super().OutputStream(**kw)

            def _terminate(self):
                if not self.up:
                    raise RuntimeError("Error terminating PortAudio: PortAudio not initialized")
                self.up = False

            def _initialize(self):
                if self.fail_start:
                    self.fail_start -= 1
                    raise RuntimeError("Error initializing PortAudio")
                self.up = True
        sd = SD()
        out = audio.StreamOut(sd)
        data = audio.wav(b"\0\0" * 800, 8000)
        with self.assertRaises(audio.StreamBroken):
            out.play(data, lambda: 1.0, threading.Event(), 0.1)
        out.play(data, lambda: 1.0, threading.Event(), 0.1)          # the next line: started afresh, heard
        self.assertTrue(sd.blocks)

    def test_the_list_read_again_finds_the_device_again(self):
        from bv import audio
        sd = self.FakeSD()
        out = audio.StreamOut(sd)
        sd.query_hostapis = lambda i=None: [{"name": "MME", "devices": [7]}] if i is None else {"name": "MME", "devices": [7]}
        sd.query_devices = lambda i: {"max_output_channels": 2}
        sd._terminate, sd._initialize = (lambda: None), (lambda: None)
        out.reopen()
        self.assertEqual(out.device, 7)

    def test_a_turn_of_the_wheel_ramps_across_a_block(self):
        import threading
        import numpy as np
        from bv import audio
        data = audio.wav((np.full(4096, 0.25) * 32767).astype("<i2").tobytes(), 8000)
        sd = self.FakeSD()
        gains = iter([1.0] + [2.0] * 20)
        audio.StreamOut(sd).play(data, lambda: next(gains), threading.Event(), 0.5)
        second = sd.blocks[1]
        self.assertAlmostEqual(float(second[0]), 0.25, places=3)        # from the old volume...
        self.assertGreater(float(second[-1]), 0.49)                      # ...to the new one, no step at the edge
        self.assertLess(float(second[-1]), float(sd.blocks[2][0]))        # (the new one itself from the next block)
        self.assertTrue(np.all(np.diff(second) >= -1e-6))

    def test_a_cut_line_raises_nothing(self):
        # a stop while the stream failed: no StreamBroken, nothing said
        import threading
        from bv import audio

        class SD(self.FakeSD):
            def OutputStream(self, **kw):
                raise RuntimeError("device unavailable")
        stopped = threading.Event()
        stopped.set()
        audio.StreamOut(SD()).play(audio.wav(b"\0\0" * 800, 8000), lambda: 1.0, stopped, 0.1)

    def test_an_outage_after_a_heard_line_is_said_again(self):
        import time
        from bv import audio
        results = iter([audio.StreamBroken("gone"), None, audio.StreamBroken("gone again")])

        class Out:
            def play(self, data, level, stopped, length):
                result = next(results)
                if result is not None:
                    raise result
        logged = []
        p = audio.Player(8, log=logged.append, out=Out())
        p.start()
        for mark in (b"A", b"B", b"C"):
            p.play(marked_line(mark, 0.05))
        time.sleep(0.5)
        self.assertEqual([m.split(":")[1].strip().split(" —")[0] for m in logged], ["gone", "gone again"])

    @unittest.skipUnless(sys.platform == "win32", "sounddevice is installed on Windows only")
    def test_the_real_library(self):
        # the wheel, its PortAudio DLL and the private names StreamOut needs, on CI's Windows
        import sounddevice
        self.assertTrue(callable(sounddevice._terminate) and callable(sounddevice._initialize))
        self.assertIn("MME", [h["name"] for h in sounddevice.query_hostapis()])

    def test_a_selfcheck_of_this_version_passes(self):
        # an installed launcher refuses a new version whose selfcheck fails, and remembers the refusal: the real one
        # must pass here (on Windows CI too, where it looks for sounddevice)
        import subprocess
        companion = Path(__file__).resolve().parents[1]
        run = subprocess.run([sys.executable, "-m", "bv.selfcheck"], cwd=companion, capture_output=True, text=True,
                             timeout=120)
        self.assertEqual(run.returncode, 0, run.stderr[-500:])

    def test_the_first_volume_is_config_jsons(self):
        from bv import audio
        self.assertEqual(audio.Player(8, gain=0.3).level(), 0.3)

    def test_a_stop_cuts_the_stream(self):
        import threading
        import time
        from bv import audio
        data = audio.wav(b"\0\0" * 80000, 8000)                         # ten seconds
        sd, stopped = self.FakeSD(blocks_wait=0.01), threading.Event()
        threading.Timer(0.1, stopped.set).start()
        started = time.monotonic()
        audio.StreamOut(sd).play(data, lambda: 1.0, stopped, audio.seconds(data))
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertTrue(sd.aborted)

    def test_the_player_reads_the_volume_asked_now(self):
        import tempfile
        import time
        from bv import audio
        heard = []

        class Out:
            def play(self, data, level, stopped, length):
                heard.append(level())
        with tempfile.TemporaryDirectory() as d:
            p = audio.Player(8, out=Out())
            p.start()
            p.set_gain(0.4)
            p.play(marked_line(b"A", 0.1))
            time.sleep(0.3)
            p.set_gain(1.6)
            p.play(marked_line(b"B", 0.1))
            time.sleep(0.3)
        self.assertEqual(heard, [0.4, 1.6])

    def test_no_device_is_said_once_and_tried_again(self):
        # no sound device at all: the line is not heard, the launcher's window says so in yellow once, and the next line
        # tries the device again (plugged in meanwhile: it plays)
        import time
        from unittest import mock
        from bv import audio, logs
        logged, played, fake = [], *fake_out()
        tries = {"n": 0}

        def stream_out(**_options):
            tries["n"] += 1
            if tries["n"] <= 2:
                raise OSError("PortAudio: no device")
            return fake
        with mock.patch.object(audio, "StreamOut", side_effect=stream_out):
            p = audio.Player(8, log=logged.append)
            p.start()
            for mark in (b"A", b"B", b"C"):
                p.play(marked_line(mark, 0.05))
            time.sleep(0.6)
        self.assertEqual(played, [b"C"])
        self.assertEqual(len(logged), 1, logged)
        self.assertTrue(logged[0].startswith("звук не играет: не открылось звуковое устройство"), logged)
        self.assertEqual(logs.level_of(logged[0]), "WARN")

    def test_a_stream_waits_longer_for_its_first_block(self):
        # a device waking up (a headset switched on) gives its first block late: FIRST_STALL for a stream's first
        # block, STALL after it - each stream its own, the one after a reopen() too
        import threading
        from unittest import mock
        from bv import audio
        data = audio.wav(b"\0\1" * 800, 8000)
        # margins wide enough for a loaded machine (the whole suite at once): STALL 0.3, FIRST_STALL 1.5, late 0.8
        with mock.patch.object(audio.StreamOut, "STALL", 0.3), mock.patch.object(audio.StreamOut, "FIRST_STALL", 1.5):
            sd = self.FakeSD(first_wait=0.8)                  # later than STALL, sooner than FIRST_STALL: plays
            audio.StreamOut(sd).play(data, lambda: 1.0, threading.Event(), 0.2)
            self.assertTrue(sd.blocks)
        with mock.patch.object(audio.StreamOut, "STALL", 0.2), mock.patch.object(audio.StreamOut, "FIRST_STALL", 0.3):
            sd = self.FakeSD(first_wait=0.9)                  # later than FIRST_STALL: stalled twice, given up
            out = audio.StreamOut(sd)
            out.reopen = lambda: setattr(sd, "aborted", False)
            with self.assertRaises(audio.StreamBroken):
                out.play(data, lambda: 1.0, threading.Event(), 0.2)

        class Stalls:
            """The first stream gives two blocks and then nothing for 0.8 s (past STALL: a stall in mid-line, the device
            gone); the one after reopen() gives its first block 0.8 s late (a headset switched on: within its own
            FIRST_STALL), then the rest."""
            CallbackStop = self.FakeSD.CallbackStop

            def __init__(self):
                self.streams, self.blocks = 0, []

            def OutputStream(self, samplerate, channels, dtype, blocksize, callback, finished_callback, device=None):
                import numpy as np
                sd, number = self, self.streams + 1
                self.streams = number
                stop = threading.Event()

                class Stream:
                    def start(self):
                        def run():
                            time.sleep(0.8 if number > 1 else 0)
                            given = 0
                            while not stop.is_set():
                                if number == 1 and given == 2 and stop.wait(0.8):
                                    break                   # a 0.8 s hole in mid-line: past STALL, a stall
                                out = np.zeros((blocksize, channels), dtype="float32")
                                try:
                                    callback(out, blocksize, None, None)
                                except sd.CallbackStop:
                                    sd.blocks.append(number)
                                    break
                                sd.blocks.append(number)
                                given += 1
                            finished_callback()
                        threading.Thread(target=run, daemon=True).start()

                    def abort(self):
                        stop.set()

                    def close(self):
                        pass
                return Stream()
        import time
        long = audio.wav(b"\0\1" * 8000, 8000)
        with mock.patch.object(audio.StreamOut, "STALL", 0.3), mock.patch.object(audio.StreamOut, "FIRST_STALL", 1.5):
            sd = Stalls()
            out = audio.StreamOut(sd)
            out.reopen = lambda: None
            out.play(long, lambda: 1.0, threading.Event(), 1.0)  # the second stream's own first block: FIRST_STALL
        self.assertEqual(sd.streams, 2)
        self.assertEqual(sd.blocks[:2], [1, 1])
        self.assertEqual(sd.blocks[-1], 2)

    def test_the_device_is_checked_at_the_start(self):
        # a moment of silence through the output at the start: a device that does not open is said before any line
        import time
        from unittest import mock
        from bv import audio
        logged, (played, fake) = [], fake_out()
        p = audio.Player(8, log=logged.append, out=fake)
        p.start()
        p.check()
        deadline = time.monotonic() + 5                 # the player's thread in its time: a loaded machine is slower
        while not played and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertEqual(played, [b"\0"])
        self.assertEqual(logged, [])
        with mock.patch.object(audio, "StreamOut", side_effect=OSError("PortAudio: no device")):
            p = audio.Player(8, log=logged.append)
            p.start()
            p.check()
            deadline = time.monotonic() + 5             # inside the patch: the thread opens the output after check()
            while not logged and time.monotonic() < deadline:
                time.sleep(0.02)
            time.sleep(0.1)                             # and nothing more said after the first word
        self.assertEqual(len(logged), 1, logged)
        self.assertTrue(logged[0].startswith("звук не играет: не открылось звуковое устройство"), logged)

    def test_the_sound_mapper_is_the_device(self):
        # Windows' sound mapper (MME's first output) follows the default output, as winsound does
        from bv import audio
        sd = self.FakeSD()
        sd.query_hostapis = lambda i=None: ([{"name": "MME", "devices": [0, 1, 2]}, {"name": "WASAPI", "devices": [3]}]
                                           if i is None else [{"name": "MME", "devices": [0, 1, 2]}][i])
        sd.query_devices = lambda i: {"max_output_channels": 0 if i == 0 else 2}      # 0 is an input
        self.assertEqual(audio.StreamOut(sd).device, 1)
        self.assertIsNone(audio.StreamOut(self.FakeSD()).device)                     # no MME: the default device

    def test_always_mme(self):
        # MME's sound mapper plays every line - WASAPI is gone (docs/adr/0010: it did not follow Windows' default output);
        # the log names what played. config.json's old audio_wasapi does nothing
        import threading
        from bv import audio
        from bv.__main__ import DEFAULT_CONFIG
        self.assertNotIn("audio_wasapi", DEFAULT_CONFIG)
        self.assertIs(DEFAULT_CONFIG["f5_first_sentence"], True)
        base = self.FakeSD

        class SD(base):
            def __init__(self):
                super().__init__()
                self.opened = []

            def query_hostapis(self, i=None):
                apis = [{"name": "MME", "devices": [0, 1]}, {"name": "Windows WASAPI", "devices": [5],
                                                              "default_output_device": 5}]
                return apis if i is None else apis[i]

            def query_devices(self, i):
                return {"max_output_channels": 2}

            def OutputStream(self, samplerate, channels, dtype, blocksize, callback, finished_callback=None,
                             device=None, extra_settings=None):
                self.opened.append((device, extra_settings))
                return base.OutputStream(self, samplerate, channels, dtype, blocksize, callback,
                                         finished_callback or (lambda: None), device)
        sd = SD()
        out = audio.StreamOut(sd)
        out.play(audio.wav(b"\0\1" * 800, 8000), lambda: 1.0, threading.Event(), 0.1)
        self.assertEqual(sd.opened, [(0, None)])
        self.assertEqual(out.api, "MME")
        self.assertIsNotNone(out.first_block)

    def test_the_first_sound_is_logged_from_the_lines_arrival(self):
        import time
        from bv import audio, logs
        logged = []

        class Out:
            api, latency, first_block = "MME", 0.12, None

            def play(self, data, level, stopped, length):
                self.first_block = time.monotonic()
        p = audio.Player(8, log=logged.append, out=Out())
        p.start()
        p.play(marked_line(b"A", 0.01), received=time.monotonic() - 0.5)
        p.play(marked_line(b"B", 0.01))                                        # no arrival: no line in the log
        time.sleep(0.3)
        p.play(marked_line(b"C", 0.01), received=time.monotonic() - 1.5)      # each line its own first block
        time.sleep(0.3)
        self.assertEqual(len(logged), 2, logged)
        self.assertRegex(logged[0], r"^    до звука 0\.5\d с \(MME, задержка выхода 120 мс\)$")
        self.assertRegex(logged[1], r"^    до звука 1\.5\d с ")
        self.assertEqual(logs.level_of(logged[0]), "DEBUG")
        # the stream's own: a new line forgets the last one's first block
        import threading
        sd = self.FakeSD()
        out = audio.StreamOut(sd)
        out.play(audio.wav(b"\0\1" * 800, 8000), lambda: 1.0, threading.Event(), 0.1)
        first = out.first_block
        time.sleep(0.05)
        out.play(audio.wav(b"\0\1" * 800, 8000), lambda: 1.0, threading.Event(), 0.1)
        self.assertGreater(out.first_block, first)

    def test_a_line_played_again_says_no_first_sound(self):
        # cut by CatQuest and played again from its start: «до звука» was said the first time, not again
        import time
        from bv import audio
        logged = []

        class Out:
            api, latency, first_block = "MME", 0.0, None

            def play(self, data, level, stopped, length):
                self.first_block = time.monotonic()
                stopped.wait(length)
        p = audio.Player(8, log=logged.append, out=Out())
        p.start()
        p.play(marked_line(b"A", 0.4), received=time.monotonic())
        time.sleep(0.1)
        p.pause()
        time.sleep(0.1)
        p.resume()
        time.sleep(0.8)
        self.assertEqual(len([m for m in logged if "до звука" in m]), 1, logged)

    def test_a_device_gone_mid_line_is_found_again(self):
        # the stream stalls (headphones pulled out): PortAudio's list read again, the line goes on from where it was
        import threading
        import numpy as np
        from unittest import mock
        from bv import audio
        pcm = (np.arange(16000) % 100).astype("<i2").tobytes()          # 2 s at 8 kHz, every sample known
        data = audio.wav(pcm, 8000)
        test = self

        class SD(self.FakeSD):
            def __init__(self):
                super().__init__()
                self.opened, self.reopened = 0, 0

            def OutputStream(self, **kw):
                self.opened += 1
                stream = test.FakeSD.OutputStream(self, **kw)
                if self.opened == 1:                     # the first stream: three blocks, then nothing more
                    real = kw["callback"]
                    calls = {"n": 0}

                    def stalling(out, frames, t, st):
                        calls["n"] += 1
                        if calls["n"] > 3:
                            time.sleep(10)
                        real(out, frames, t, st)
                    kw = dict(kw, callback=stalling)
                    stream = test.FakeSD.OutputStream(self, **kw)
                return stream

            def _terminate(self):
                self.reopened += 1

            def _initialize(self):
                self.aborted = False
        import time
        sd = SD()
        with mock.patch.object(audio.StreamOut, "STALL", 0.2):
            out = audio.StreamOut(sd)
            out.play(data, lambda: 1.0, threading.Event(), audio.seconds(data))
        self.assertEqual((sd.opened, sd.reopened), (2, 1))
        played = np.concatenate(sd.blocks)
        resumed = round(float(played[3 * 1024]) * 32768)                  # the first sample after the stall
        self.assertEqual(resumed, (3 * 1024) % 100, "on from where it stopped, not from the start")

    def test_a_stream_that_breaks_is_said_and_the_next_line_tries(self):
        # the device gone for good (twice for one line, the list read again between): said once, the line not heard,
        # the next line tries the device again
        import time
        from bv import audio, logs

        class Broken:
            class PortAudioError(Exception):
                pass

            def __init__(self):
                self.opened = 0

            def OutputStream(self, **kwargs):
                self.opened += 1
                raise self.PortAudioError("device unavailable")

            def _terminate(self):
                pass

            def _initialize(self):
                pass
        logged, sd = [], Broken()
        p = audio.Player(8, log=logged.append, out=audio.StreamOut(sd))
        p.start()
        p.play(marked_line(b"A", 0.1))
        p.play(marked_line(b"B", 0.1))
        time.sleep(0.8)
        self.assertEqual(sd.opened, 4)                              # each line: twice, the list read again between
        self.assertEqual(len(logged), 1, logged)

        self.assertTrue(logged[0].startswith("звук не играет: device unavailable"), logged)
        self.assertEqual(logs.level_of(logged[0]), "WARN")


class PlayerErrors(unittest.TestCase):
    """The player is the only one: a line that fails to play is logged and the next ones still play
    (it was the thread's end, and the companion went silent for good)."""

    def test_goes_on_after_a_failed_line(self):
        import tempfile
        import time
        played, fake = fake_out(fail_first=True)
        logged = []
        from bv.audio import Player
        from bv.logs import level_of
        with tempfile.TemporaryDirectory() as d:
            p = Player(2, log=logged.append, out=fake)
            p.start()
            for mark in (b"A", b"B", b"C"):
                p.play(marked_line(mark, 0.05))
            time.sleep(1.0)
            self.assertTrue(p.is_alive())
            self.assertEqual(played, [b"B", b"C"])
            self.assertEqual(logged, ["не удалось проиграть строку: Failed to play sound"])
            self.assertEqual(level_of(logged[0]), "WARN")
            self.assertGreater(p.quiet_for(), 0)


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

    def test_a_dropped_battle_net_line_logged_without_the_digits(self):
        import queue
        from bv.audio import queue_line
        from bv.protocol import parse
        q, said = queue.Queue(), []
        friend = parse("\x1f".join(["whisper", "BN:Вася#1234", "", "", "", "", "rate=100", "привет"]).encode())
        queue_line(q, friend, 1, said.append)
        queue_line(q, self.line("l0"), 1, said.append)
        self.assertEqual(said, ["очередь полна (1): не прочитано: BN:Вася: привет"])

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

    def accentor_with(self, d, offline=False, error=None):
        """An Accentor over a stand-in RUAccent that downloads, as the real one, only a folder that is not there:
        dictionary/ with yo_words.json.gz, and its package's koziev/."""
        import sys
        import types
        from unittest import mock

        import numpy  # noqa: F401 - before sys.modules is patched: its restore would drop a numpy loaded under it
        from bv.text import Accentor
        package = Path(d) / "site" / "ruaccent"
        downloads = []

        class RUAccent:
            def __init__(self):
                self.module_path = str(package)

            def load(self, omograph_model_size, use_dictionary, tiny_mode, workdir):
                if error is not None:
                    raise error
                folder = Path(workdir) / "dictionary"
                if not folder.exists():
                    if os.environ.get("HF_HUB_OFFLINE") == "1":       # as huggingface_hub: no asking the hub
                        from huggingface_hub.errors import OfflineModeIsEnabled
                        raise OfflineModeIsEnabled("offline mode is enabled")
                    downloads.append("dictionary")
                    folder.mkdir(parents=True)
                    (folder / "yo_words.json.gz").write_bytes(b"x")
                if not (package / "koziev").exists():
                    (package / "koziev").mkdir(parents=True)
                (folder / "yo_words.json.gz").read_bytes()             # FileNotFoundError when it is not there
        env = {"HF_HOME": str(Path(d) / "hf"), **({"HF_HUB_OFFLINE": "1"} if offline else {})}
        patches = [mock.patch.dict(os.environ, env), mock.patch.dict(sys.modules, {"ruaccent": types.SimpleNamespace(RUAccent=RUAccent)})]
        logged = []
        return Accentor(logged.append), patches, logged, downloads

    def cut_download(self, d):
        folder = Path(d) / "hf" / "ruaccent" / "dictionary"
        folder.mkdir(parents=True)
        (folder / "omographs.json.gz").write_bytes(b"x")                # yo_words.json.gz never came
        return folder

    def test_a_cut_download_is_fetched_again(self):
        # beta 20: the first start stopped during «загружаю RUAccent ...»; every later start, online, ended on
        # «FileNotFoundError: … yo_words.json.gz» - RUAccent fetches a folder only when it is not there
        from contextlib import ExitStack
        from bv.logs import level_of
        with tempfile.TemporaryDirectory() as d:
            accentor, patches, logged, downloads = self.accentor_with(d)
            folder = self.cut_download(d)
            with ExitStack() as stack:
                for p in patches:
                    stack.enter_context(p)
                os.environ.pop("HF_HUB_OFFLINE", None)
                accentor.load()
            self.assertIsNotNone(accentor.model)
            self.assertEqual(downloads, ["dictionary"])
            self.assertTrue((folder / "yo_words.json.gz").exists())
            self.assertEqual(logged[0], "загрузка RUAccent в прошлый раз оборвалась — удаляю недокачанное и скачиваю заново")
            self.assertEqual(level_of(logged[0]), "WARN")
            self.assertIn("FileNotFoundError", logged[1])
            self.assertEqual(level_of(logged[1]), "DEBUG")

    def test_offline_the_cut_download_is_cleared_and_the_start_goes_online(self):
        # the models' mark set (they loaded once), a file gone since: offline the folders are cleared all the same,
        # and RUAccent asking the hub for them raises what models_missing takes for a start online
        from contextlib import ExitStack
        from bv.f5engine import models_missing
        with tempfile.TemporaryDirectory() as d:
            accentor, patches, logged, downloads = self.accentor_with(d, offline=True)
            folder = self.cut_download(d)
            with ExitStack() as stack:
                for p in patches:
                    stack.enter_context(p)
                with self.assertRaises(Exception) as raised:
                    accentor.load()
            self.assertTrue(models_missing(raised.exception), raised.exception)
            self.assertFalse(folder.exists())                                       # online it is fetched whole
            self.assertEqual(logged[0], "загрузка RUAccent в прошлый раз оборвалась — удаляю недокачанное и скачиваю заново")
            self.assertEqual(downloads, [])

    def test_another_error_leaves_the_files(self):
        # an error that is no missing file is no reason to download 0.7 GB again: no network, a file held, a model
        # that does not start
        from contextlib import ExitStack
        from huggingface_hub.errors import OfflineModeIsEnabled
        for error in (RuntimeError("onnxruntime: bad"), PermissionError(13, "held"), TimeoutError("timed out"),
                      ConnectionResetError(104, "reset"), OfflineModeIsEnabled("offline mode is enabled")):
            with self.subTest(error=type(error).__name__), tempfile.TemporaryDirectory() as d:
                accentor, patches, logged, downloads = self.accentor_with(d, error=error)
                folder = self.cut_download(d)
                with ExitStack() as stack:
                    for p in patches:
                        stack.enter_context(p)
                    os.environ.pop("HF_HUB_OFFLINE", None)
                    with self.assertRaises(type(error)):
                        accentor.load()
                self.assertTrue((folder / "omographs.json.gz").exists())                 # nothing removed
                self.assertEqual((logged, downloads), ([], []))

    def test_missing_file_is_a_file_not_there(self):
        from bv.text import missing_file
        NoSuchFile = type("NoSuchFile", (RuntimeError,), {})                   # ONNX Runtime's
        for error, want in ((FileNotFoundError(2, "No such file or directory"), True), (NoSuchFile("x"), True),
                            (RuntimeError("Load model failed: No such file or directory"), True),
                            (PermissionError(13, "denied"), False), (TimeoutError(), False),
                            (ConnectionResetError(104, "reset"), False), (IsADirectoryError(21, "dir"), False),
                            (RuntimeError("bad"), False)):
            with self.subTest(error=repr(error)):
                self.assertEqual(missing_file(error), want)

    def test_clear_ruaccent_removes_the_folders_it_checks(self):
        from unittest import mock
        from bv.text import clear_ruaccent
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"HF_HOME": str(Path(d) / "hf")}):
            root, package = Path(d) / "hf" / "ruaccent", Path(d) / "site" / "ruaccent"
            for folder in (root / "dictionary", root / "nn" / "nn_omograph" / "turbo3.1", root / "nn" / "nn_accent",
                           root / "koziev", package / "koziev"):
                folder.mkdir(parents=True)
                (folder / "f").write_bytes(b"x")
            removed = clear_ruaccent("turbo3.1", str(package))
            self.assertEqual(len(removed), 4)
            self.assertTrue((root / "nn" / "nn_accent" / "f").exists())     # fetched before dictionary: whole
            self.assertFalse(any(f.exists() for f in removed))


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

    def setup(self, d, fade="true", enabled="true", status=None, saved_at=900_000):
        saved = Path(d) / "_forever_" / "WTF" / "Account" / "X" / "SavedVariables"
        saved.mkdir(parents=True)
        (saved / "BarrensVoice.lua").write_text(f'BarrensVoiceDB = {{\n["fadeChat"] = {fade},\n["enabled"] = {enabled},\n}}\n',
                                                 encoding="utf-8")
        os.utime(saved / "BarrensVoice.lua", (saved_at, saved_at))   # when the game wrote them: /reload, logout
        addon = Path(d) / "_forever_" / "Interface" / "AddOns" / "BarrensVoice"
        addon.mkdir(parents=True)
        if status:
            (addon / "CompanionStatus.lua").write_text(f"BarrensVoiceStatus = {status}\n", encoding="utf-8")
        return {"game_dirs": {"forever": str(Path(d) / "_forever_")}}, addon

    def test_cases(self):
        from bv.reloadhint import needed
        now = 1_000_000
        cases = [  # (fade, enabled, status file, strip in view[, saved variables written at]) -> remind
            (("true", "true", None, True), True),
            (("true", "true", None, False), False),                          # at character select: no
            (("false", "true", None, True), False),                          # the hidden chat off
            (("true", "false", None, True), False),                          # the addon switched off
            (("true", "true", "{ beat = 0, stopped = 999990 }", True), False),   # a restart: the addon saw the last one
            (("true", "true", "{ beat = 999000 }", True), True),             # an old beat: nobody at login
            # stopped 49 s ago, but a /reload since (the saved variables are newer): the addon loaded without it
            (("true", "true", "{ beat = 999940, stopped = 999951 }", True, 999970), True),
            # a /reload begun a few seconds before the stop: the addon may have read the status after it - reminded
            (("true", "true", "{ beat = 0, stopped = 999951 }", True, 999945), True),
            # the launcher's restart: no /reload between the stop and the start
            (("true", "true", "{ beat = 999940, stopped = 999951 }", True, 999000), False),
            (("true", "true", "{ beat = 999990, stopped = 0 }", True, 999980), False),   # running at that /reload: seen
            # killed (no stop written): the addon takes a beat for 45 s - a /reload well within them saw it, a later
            # one (or one in the last RELOAD_SLACK seconds of them) not
            (("true", "true", "{ beat = 999950 }", True, 999970), False),
            (("true", "true", "{ beat = 999950 }", True, 999990), True),
            (("true", "true", "{ beat = 999940 }", True, 999990), True),
        ]
        for (fade, enabled, status, in_view, *at), want in cases:
            with self.subTest(fade=fade, enabled=enabled, status=status, in_view=in_view, at=at):
                with tempfile.TemporaryDirectory() as d:
                    config, addon = self.setup(d, fade, enabled, status, *at)
                    self.assertEqual(needed(config, addon, in_view=lambda c: in_view, now=now), want)


class LogLevels(unittest.TestCase):
    def test_levels(self):
        from bv.logs import level_of
        cases = {
            "игра закрыта — выключаю озвучку": "INFO",
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
            "полоска аддона пропала: озвучка выключена в игре (/bv off), экран загрузки или полоску закрыл другой аддон?": "WARN",
            "если окно чата не прячется — /reload в игре": "WARN",
            # where the strip is taken from at start: details, whichever the source
            "полоска (по сохранённым настройкам аддона): верх, x 0, y 0, ширина 1920 (экран 1920×1080)": "DEBUG",
            "полоска (где её последний раз видел лаунчер — новее сохранённых настроек аддона): верх, x 0, y 0, "
            "ширина 1920 (экран 1920×1080)": "DEBUG",
            "Голоса рас недоступны, читаю голосами Windows.": "WARN",
            "ОШИБКА (озвучка): KeyError: 1": "ERROR",
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


if __name__ == "__main__":
    unittest.main()
