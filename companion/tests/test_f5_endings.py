"""tools/f5_endings.py's cases: the Whisper verdicts of a log with the chat line each was for."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))                    # bv, for pieces()
import f5_endings  # noqa: E402

LOG = """\
10:00:00 CHAT  [канал 2. Общий: Степи] Вася Пупкин (Orc, м) → orc-male/standard: Вася Пупкин пишет: ку
10:00:00 DEBUG     исходно:   ку
10:00:00 DEBUG     к синтезу: В+ася П+упкин п+ишет: ку.
10:00:01 DEBUG     конец цел (Whisper: «Вася Пупкин пишет ку.»)
10:00:02 DEBUG     до звука 1.10 с (MME, задержка выхода 213 мс)
10:01:00 CHAT  [гильдия] Тётя Мотя (Scourge, ж) → scourge-female^-1.5: Тётя Мотя пишет: всем привет. как дела
10:01:00 DEBUG     к синтезу: Тётя М+отя п+ишет: всем прив+ет. как дел+а?  (2 части)
10:01:01 DEBUG     конец обрезан, ещё раз длиннее (Whisper: «Тётя Мотя пишет, всем привет, как де»)
10:02:00 CHAT  [канал 2. Общий: Степи] Без Проверки (Orc, м) → orc-male: Без Проверки пишет: привет
10:02:00 DEBUG     к синтезу: Без Пров+ерки п+ишет: прив+ет.
""".splitlines()


class Cases(unittest.TestCase):
    def test_the_verdicts_with_their_lines(self):
        found = f5_endings.cases(LOG)
        self.assertEqual([(c["name"], c["voice"], c["verdict"]) for c in found],
                         [("Тётя Мотя", "scourge-female^-1.5", "cut"), ("Вася Пупкин", "orc-male/standard", "whole")])
        self.assertEqual(found[0]["text"], "Тётя М+отя п+ишет: всем прив+ет. как дел+а?")     # «(2 части)» dropped
        self.assertEqual(found[0]["heard"], "Тётя Мотя пишет, всем привет, как де")

    def test_lines_waiting_in_the_queue(self):
        # chat lines are logged as they come, their synthesis later: a verdict goes to its own line, not the last one
        log = """\
11:00:00 CHAT  [гильдия] Вася Пупкин (Orc, м) → orc-male/standard: Вася Пупкин пишет: продам сумки недорого
11:00:00 CHAT  [гильдия] Тётя Мотя (Scourge, ж) → scourge-female^-1.5: Тётя Мотя пишет: LFW Enchanting, PST!
11:00:01 DEBUG     к синтезу: В+ася П+упкин п+ишет: прод+ам с+умки недор+ого.
11:00:02 DEBUG     конец обрезан, ещё раз длиннее (Whisper: «Вася Пупкин пишет, продам сумки недоро»)
11:00:03 DEBUG     до звука 2.10 с (MME, задержка выхода 213 мс)
11:00:04 DEBUG     конец обрезан, ещё раз длиннее (Whisper: «Тётя Мотя пишет. Эл эф дабл ю»)
11:00:05 DEBUG     до звука 3.00 с (MME, задержка выхода 213 мс)
""".splitlines()
        found = f5_endings.cases(log)
        self.assertEqual([(c["name"], c["voice"]) for c in found],
                         [("Вася Пупкин", "orc-male/standard"), ("Тётя Мотя", "scourge-female^-1.5")])
        self.assertEqual(found[0]["text"], "В+ася П+упкин п+ишет: прод+ам с+умки недор+ого.")
        self.assertEqual(found[1]["text"], "Тётя Мотя пишет: LFW Enchanting, PST!")    # no «к синтезу»: as typed

    def test_a_line_of_several_pieces(self):
        # each verdict is for one F5 call: the line's whole text is kept, the lab picks the piece by what was heard
        log = """\
12:00:00 CHAT  [канал 2. Общий: Степи] Вася Пупкин (Orc, м) → orc-male: Вася Пупкин пишет: Открою портал в город. 50с за порт
12:00:00 DEBUG     к синтезу: В+ася П+упкин п+ишет: Откр+ою порт+ал в г+ород. пятьдес+ят серебр+а за порт.
12:00:01 DEBUG     конец обрезан, ещё раз длиннее (Whisper: «Вася Пупкин пишет. Открою портал в горо»)
12:00:02 DEBUG     до звука 1.50 с (MME, задержка выхода 213 мс)
12:00:03 DEBUG     конец цел (Whisper: «Пятьдесят серебра за порт.»)
""".splitlines()
        found = f5_endings.cases(log)
        self.assertEqual([(c["name"], c["verdict"]) for c in found], [("Вася Пупкин", "cut"), ("Вася Пупкин", "whole")])
        self.assertTrue(all(c["text"].startswith("В+ася П+упкин") for c in found))

    def test_the_piece_heard(self):
        # the lab makes the F5 call the verdict was for, cut as render() cuts a line (first sentence, groups)
        import types
        speaker = types.SimpleNamespace(config={}, ref_seconds={"v": 3.0},
                                        duration=lambda slot, text, rate, character: 3.0 + 0.05 * len(text))
        slot = types.SimpleNamespace(id="v")
        text = "В+ася П+упкин п+ишет: Откр+ою порт+ал в г+ород. пятьдес+ят серебр+а за порт."
        self.assertEqual(f5_endings.pieces(speaker, slot, text, "Вася Пупкин"),
                         ["В+ася П+упкин п+ишет: Откр+ою порт+ал в г+ород.", "пятьдес+ят серебр+а за порт."])
        cut = {"text": text, "name": "Вася Пупкин", "heard": "Вася Пупкин пишет. Открою портал в горо"}
        self.assertEqual(f5_endings.piece_heard(speaker, slot, cut), "В+ася П+упкин п+ишет: Откр+ою порт+ал в г+ород.")
        self.assertEqual(f5_endings.piece_heard(speaker, slot, {**cut, "heard": "Пятьдесят серебра за порт."}),
                         "пятьдес+ят серебр+а за порт.")

    def test_a_weak_match_is_no_match(self):
        # a Latin line Whisper hears in Cyrillic matches its own text worse than a Russian line before it: under
        # FLOOR the oldest waiting line takes the verdict (the synthesis thread takes lines in turn)
        log = """\
13:00:00 CHAT  [гильдия] Вася Пупкин (Orc, м) → orc-male: Вася Пупкин пишет: идём в пещеры стенаний
13:00:01 DEBUG     к синтезу: В+ася П+упкин п+ишет: идём в пещ+еры стен+аний.
13:00:02 DEBUG     конец цел (Whisper: «Вася Пупкин пишет, идём в пещеры стенаний.»)
13:00:03 CHAT  [канал 2. Общий: Степи] Frank Smith (Human, м) → human-male: LFW Enchanting, PST!
13:00:03 CHAT  [канал 2. Общий: Степи] Joe Black (?) → orc-male^+1.5: LFM DM, need heal
13:00:04 DEBUG     конец обрезан, ещё раз длиннее (Whisper: «Эл эф дабл ю энчантинг пи эс»)
13:00:06 DEBUG     конец обрезан, ещё раз длиннее (Whisper: «Эл эф эм ди эм нид хил»)
""".splitlines()
        found = {c["heard"][:6]: c for c in f5_endings.cases(log)}
        cut = [c for c in f5_endings.cases(log) if c["verdict"] == "cut"]
        self.assertEqual([(c["name"], c["voice"], c["text"]) for c in cut],
                         [("Frank Smith", "human-male", "LFW Enchanting, PST!"),
                          ("Joe Black", "orc-male^+1.5", "LFM DM, need heal")])
        self.assertTrue(all(c["match"] < f5_endings.FLOOR for c in cut))      # a weak pairing shows in the case
        self.assertEqual(found["Вася П"]["match"], 1.0)

    def test_synthesis_goes_to_the_line_its_text_matches(self):
        # not simply the oldest: a line dropped before synthesis (the queue full) must not take the next line's text
        log = """\
14:00:00 CHAT  [гильдия] Вася Пупкин (Orc, м) → orc-male: Вася Пупкин пишет: продам сумки
14:00:00 CHAT  [гильдия] Тётя Мотя (Scourge, ж) → scourge-female: Тётя Мотя пишет: всем привет
14:00:01 DEBUG     к синтезу: Тётя М+отя п+ишет: всем прив+ет.
14:00:02 DEBUG     конец обрезан, ещё раз длиннее (Whisper: «Тётя Мотя пишет, всем при»)
""".splitlines()
        self.assertEqual([c["name"] for c in f5_endings.cases(log)], ["Тётя Мотя"])
        # the line before it is not waiting any more, and «?» never was: a weak verdict after goes to a later line
        log += """\
14:00:03 CHAT  [гильдия] Тётя Мотя (Scourge, ж) → scourge-female: ?
14:00:04 CHAT  [гильдия] Frank Smith (Human, м) → human-male: gg wp
14:00:05 DEBUG     конец обрезан, ещё раз длиннее (Whisper: «Гэ гэ вэ пэ»)
""".splitlines()
        self.assertEqual([c["name"] for c in f5_endings.cases(log)], ["Тётя Мотя", "Frank Smith"])

    def test_pieces_at_the_players_speed(self):
        # a long line is cut by its seconds, and those depend on the addon's speed; a question is a call of its own
        import types
        speaker = types.SimpleNamespace(config={"f5_part_seconds": 5}, ref_seconds={"v": 3.0},
                                        duration=lambda slot, text, rate, character: 3.0 + 0.05 * len(text) * 100 / rate)
        slot = types.SimpleNamespace(id="v")
        text = "В+ася п+ишет: идём в рейд. кто с н+ами, пиш+ите в л+ичку, ждём до в+осьми, потом уходим. есть танк?"
        slow = f5_endings.pieces(speaker, slot, text, "Вася", rate=70)
        fast = f5_endings.pieces(speaker, slot, text, "Вася", rate=200)
        self.assertGreater(len(slow), len(fast))
        self.assertEqual(fast[-1], "есть танк?")                               # sentence_groups: the question apart
        case = {"text": text, "name": "Вася", "heard": "ждём до восьми"}
        self.assertIn(f5_endings.piece_heard(speaker, slot, case, rate=70), slow)
        self.assertNotIn(f5_endings.piece_heard(speaker, slot, case, rate=70), fast)
        self.assertEqual(f5_endings.plain("Ёлки, Ё+ЖИК 5!"), "елки ежик 5")

    def test_a_weak_second_verdict_stays_with_the_line_being_made(self):
        # a Latin line of two calls, a new line logged between its verdicts: the second (weak) verdict is still its own,
        # and the new line keeps its «к синтезу» text
        log = """\
15:00:00 CHAT  [канал 2. Общий: Степи] Frank Smith (Human, м) → human-male: LFW Enchanting, all recipes up to 300. PST me for mats please!
15:00:01 DEBUG     конец обрезан, ещё раз длиннее (Whisper: «Эл эф дабл ю энчантинг, ол рецептс ап ту 300»)
15:00:02 CHAT  [гильдия] Вася Пупкин (Orc, м) → orc-male: Вася Пупкин пишет: продам сумки
15:00:03 DEBUG     конец обрезан, ещё раз длиннее (Whisper: «Пи эс ти ми фор матс плиз»)
15:00:04 DEBUG     к синтезу: В+ася П+упкин п+ишет: прод+ам с+умки.
15:00:05 DEBUG     конец цел (Whisper: «Вася Пупкин пишет, продам сумки.»)
""".splitlines()
        found = f5_endings.cases(log)
        self.assertEqual(sorted((c["name"], c["heard"][:6], c["text"]) for c in found),
                         [("Frank Smith", "Пи эс ", "LFW Enchanting, all recipes up to 300. PST me for mats please!"),
                          ("Frank Smith", "Эл эф ", "LFW Enchanting, all recipes up to 300. PST me for mats please!"),
                          ("Вася Пупкин", "Вася П", "В+ася П+упкин п+ишет: прод+ам с+умки.")])

    def test_a_synthesis_whose_chat_line_is_not_in_the_log(self):
        # the log began later: a weak «к синтезу» is no line in the log - its verdicts are dropped, not given away
        log = """\
16:00:00 CHAT  [гильдия] Вася Пупкин (Orc, м) → orc-male: Вася Пупкин пишет: продам сумки
16:00:01 DEBUG     к синтезу: Тётя М+отя п+ишет: всем прив+ет.
16:00:02 DEBUG     конец обрезан, ещё раз длиннее (Whisper: «Тётя Мотя пишет, всем при»)
16:00:03 DEBUG     к синтезу: В+ася П+упкин п+ишет: прод+ам с+умки.
16:00:04 DEBUG     конец цел (Whisper: «Вася Пупкин пишет, продам сумки.»)
""".splitlines()
        self.assertEqual([(c["name"], c["verdict"]) for c in f5_endings.cases(log)], [("Вася Пупкин", "whole")])

    def test_numbers_heard_as_digits_stay_with_their_line(self):
        # «сто двести триста» heard as «100, 200, 3»: weak against its own line, still its own while another waits
        log = """\
17:00:00 CHAT  [гильдия] Вася Пупкин (Orc, м) → orc-male: 100 200 300
17:00:00 CHAT  [гильдия] Тётя Мотя (Scourge, ж) → scourge-female: всем привет
17:00:01 DEBUG     к синтезу: сто дв+ести тр+иста.
17:00:02 DEBUG     конец обрезан, ещё раз длиннее (Whisper: «100, 200, 3»)
""".splitlines()
        self.assertEqual([c["name"] for c in f5_endings.cases(log)], ["Вася Пупкин"])

    def test_a_misheard_word_is_still_a_match(self):
        # one word misheard in a Russian line: over FLOOR, so not handed to the waiting line
        log = """\
18:00:00 CHAT  [гильдия] Вася Пупкин (Orc, м) → orc-male: Вася Пупкин пишет: продам сумки на шестнадцать слотов
18:00:01 DEBUG     к синтезу: В+ася П+упкин п+ишет: прод+ам с+умки на шестн+адцать сл+отов.
18:00:01 CHAT  [гильдия] Тётя Мотя (Scourge, ж) → scourge-female: Тётя Мотя пишет: всем привет
18:00:02 DEBUG     конец цел (Whisper: «Вася Купкин пишет, продам суммы на 16 слоёв.»)
18:00:03 DEBUG     конец цел (Whisper: «Ваца Пубкин пишит, продаем сумку на шестнадцать слоев»)
""".splitlines()
        found = f5_endings.cases(log)
        self.assertEqual([c["name"] for c in found], ["Вася Пупкин", "Вася Пупкин"])
        self.assertTrue(all(f5_endings.FLOOR <= c["match"] < 0.9 for c in found), [c["match"] for c in found])

    def test_a_latin_lines_weak_verdict_after_a_russian_line_of_two_calls(self):
        # a Cyrillic line's own verdicts match: a weak one after it is the waiting Latin line's, calls left or not
        log = """\
19:00:00 CHAT  [гильдия] Вася Пупкин (Orc, м) → orc-male: Вася Пупкин пишет: идём в пещеры стенаний все вместе. кто с нами?
19:00:01 DEBUG     к синтезу: В+ася П+упкин п+ишет: идём в пещ+еры стен+аний все вм+есте. кто с н+ами?
19:00:02 CHAT  [канал 2. Общий: Степи] Frank Smith (Human, м) → human-male: LFW Enchanting, PST!
19:00:03 DEBUG     конец обрезан, ещё раз длиннее (Whisper: «Эл эф дабл ю энчантинг пи эс»)
""".splitlines()
        self.assertEqual([c["name"] for c in f5_endings.cases(log)], ["Frank Smith"])
        alone = [line for line in log if "Frank" not in line]                    # nothing waits: its own after all
        self.assertEqual([c["name"] for c in f5_endings.cases(alone)], ["Вася Пупкин"])
        self.assertTrue(f5_endings.foreign("LFW Enchanting, PST!") and f5_endings.foreign("100, 200, 3"))
        self.assertFalse(f5_endings.foreign("В+ася П+упкин п+ишет: идём"))

    def test_a_synthesis_upgrades_the_line_a_verdict_took(self):
        # a weak verdict handed to a waiting line before its «к синтезу»: that «к синтезу» then gives it its text
        log = """\
20:00:00 CHAT  [гильдия] Вася Пупкин (Orc, м) → orc-male: Вася Пупкин пишет: ку
20:00:01 DEBUG     к синтезу: В+ася П+упкин п+ишет: ку.
20:00:02 DEBUG     конец цел (Whisper: «Вася Пупкин пишет ку.»)
20:00:03 CHAT  [гильдия] Тётя Мотя (Scourge, ж) → scourge-female: Тётя Мотя пишет: продам 20 сумок
20:00:04 DEBUG     конец обрезан, ещё раз длиннее (Whisper: «Тётя Мотя пишет, продам 20 сум»)
20:00:05 DEBUG     к синтезу: Тётя М+отя п+ишет: прод+ам дв+адцать с+умок.
20:00:06 DEBUG     конец цел (Whisper: «Тётя Мотя пишет, продам двадцать сумок.»)
""".splitlines()
        found = [c for c in f5_endings.cases(log) if c["name"] == "Тётя Мотя"]
        self.assertEqual([c["text"] for c in found], ["Тётя Мотя пишет: продам 20 сумок",
                                                      "Тётя М+отя п+ишет: прод+ам дв+адцать с+умок."])

    def test_a_strong_verdict_for_a_waiting_line_drops_the_older_ones(self):
        log = """\
21:00:00 CHAT  [гильдия] Вася Пупкин (Orc, м) → orc-male: Вася Пупкин пишет: продам сумки
21:00:00 CHAT  [гильдия] Тётя Мотя (Scourge, ж) → scourge-female: Тётя Мотя пишет: всем привет
21:00:01 DEBUG     конец цел (Whisper: «Тётя Мотя пишет, всем привет.»)
21:00:02 DEBUG     конец обрезан, ещё раз длиннее (Whisper: «Эр эр эр»)
""".splitlines()
        self.assertEqual([c["name"] for c in f5_endings.cases(log)], ["Тётя Мотя", "Тётя Мотя"])   # Вася no longer waits

    def test_exact_from_b3(self):
        # 0.6.0b3 on: every line made has its «к синтезу» - a verdict is its; a weak one (words against typed digits)
        # takes the oldest waiting line and keeps the text F5 got
        log = """\
22:00:00 CHAT  [гильдия] Вася Пупкин (Orc, м) → orc-male: 100 200 300
22:00:01 DEBUG     к синтезу: сто дв+ести тр+иста.
22:00:02 DEBUG     конец обрезан, ещё раз длиннее (Whisper: «100, 200, 3»)
22:00:03 CHAT  [канал 2. Общий: Степи] Frank Smith (Human, м) → human-male: LFW Enchanting, PST!
22:00:04 DEBUG     к синтезу: LFW Enchanting, PST!
22:00:05 DEBUG     конец обрезан, ещё раз длиннее (Whisper: «Эл эф дабл ю энчантинг пи эс»)
""".splitlines()
        found = f5_endings.cases(log, exact=True)
        self.assertEqual(sorted((c["name"], c["text"]) for c in found),
                         [("Frank Smith", "LFW Enchanting, PST!"), ("Вася Пупкин", "сто дв+ести тр+иста.")])

    def test_a_short_line_with_a_number(self):
        # «к синтезу» has the numbers in words: matched against the chat text said so, «го 5» is its own line,
        # not an orphan - and not the line the queue dropped before it
        log = """\
23:00:00 CHAT  [гильдия] Тётя Мотя (Scourge, ж) → scourge-female: Тётя Мотя пишет: продам сумки на шестнадцать
23:00:00 CHAT  [гильдия] Вася Пупкин (Orc, м) → orc-male: го 5
23:00:01 DEBUG     к синтезу: го п+ять.
23:00:02 DEBUG     конец обрезан, ещё раз длиннее (Whisper: «Го, 5»)
""".splitlines()
        for exact in (False, True):
            self.assertEqual([(c["name"], c["text"]) for c in f5_endings.cases(log, exact=exact)],
                             [("Вася Пупкин", "го п+ять.")], exact)
        self.assertTrue(f5_endings.digits("100, 200, 3") and not f5_endings.digits("Elf double you and chant in peace"))

    def test_exact_drops_an_orphans_verdicts(self):
        log = """\
23:10:00 CHAT  [гильдия] Вася Пупкин (Orc, м) → orc-male: Вася Пупкин пишет: ку
23:10:01 DEBUG     к синтезу: Тётя М+отя п+ишет: всем прив+ет.
23:10:02 DEBUG     конец обрезан, ещё раз длиннее (Whisper: «Тётя Мотя пишет, всем при»)
""".splitlines()
        self.assertEqual(f5_endings.cases(log, exact=True), [])

    def test_calls(self):
        self.assertEqual(f5_endings.calls("В+ася п+ишет: идём в рейд все вместе. кто с н+ами?"), 2)
        self.assertEqual(f5_endings.calls("а" * 600), 3)                              # a call more per 250 letters

    def test_how_many(self):
        self.assertEqual([c["verdict"] for c in f5_endings.cases(LOG, cut=0, whole=1)], ["whole"])
        self.assertEqual(f5_endings.cases(LOG, cut=1, whole=0)[0]["verdict"], "cut")


if __name__ == "__main__":
    unittest.main()
