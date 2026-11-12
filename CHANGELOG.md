# Changelog

## 0.2.0

- Race voices now come from the game client itself: the Russian voice-over of the playable races — each race and sex has the player character's voice and three NPC voice types (orc guard, shady and standard; human official, standard and warrior; …), each also in a lower and a higher copy, 12 voices per race and sex. Real actors instead of synthesized CatQuest voices: the orc sounds low and rough and the speech comes out clearer. CatQuest is no longer needed.
- The client's files are only read, never changed, and the game is not touched: the voice bank is made on your machine before the game starts, the first time and after each game update (a few minutes: Whisper hears the lines for their text), and kept until the next update.
- Slow voices speak faster: the game's recordings differ up to fourfold in tempo (a hurried error message of a character, a solemn NPC greeting), and a voice slower than the faster quarter of the voices is now drawn most of the way toward it (by at most 1.8 times; the Tauren elder went from 18.5 to 12.3 seconds on a test line); faster voices stay as they are. Each character also speaks at a tempo of their own (±8 %, from the name), so two characters given the same voice still sound like two people.
- Endings no longer get cut off: when a line's speech runs to the very end of the length given to it (one line in ten), it is made again with a quarter more length.
- The race voices load while the game starts instead of waiting for its first chat line (unless the addon was last set to Windows voices).
- Very high and very low voices no longer rasp in questions: the pitch analysis behind the question intonation had a fixed 60–500 Hz range, and gnome women speak at 450–500 Hz, the orc character at 55–70 Hz; outside the range it lost the voice's periods. It now follows the voice.
- Numbers get their stress like other words ("шестн+адцать", not "ш+естнадцать"): they are turned into words before the stress marks are put, not after.
- A line with a word the stress model splits its own way ("RU/UA", "<MIR>") no longer loses the stress marks of all its words ("игр+оков" for "игрок+ов"): only that word goes without.
- The dictionary reads Discord as «диск+орд», the Crossroads as «перекр+ёсток» and greaves as «п+оножи» in every case, «ПС» as «Пещеры стенаний», «че» as «чё», «серега» as «серёга», «пикабу» as «пикаб+у», PvE as «пэ-вэ-йе».
- A dictionary stem (an entry with `*`) keeps the case typed in chat: «на перекрёстке» was turned into «на перекрёсток», as the declension after a preposition is meant for abbreviations («в ОП») that have no ending of their own.
- Several lines in a row from one character in one channel are read as one speech: the name only before the first, when the next line comes while the previous one is still being read or within 5 seconds after it ends (someone else in between — the name again).
- The dictionary is applied by the program now: it reads the default dictionary straight from the addon's files and picks up a change within seconds, with no /reload; your edits from the dictionary window come to it as before. A character's name is no longer run through the dictionary (a character named «Лок» stays «Лок»).
- Chat lines dropped after waiting too long for CatQuest are noted in the program's log.
- A chat line dropped because the queue is full (more than 8 lines waiting in a busy chat) is noted in the program's log; before, it vanished without a trace.
- `/wcv debug`: the addon notes in the program's log each chat line it does not send, with the reason (chat type off, not shown in any chat window, hidden by another addon's chat filter, your own), and when CatQuest starts and stops speaking — the log has the time the game's chat lacks.
- The chat no longer waits for CatQuest when CatQuest reports a track still playing well past the track's own length: its «playing» gets stuck at times, and chat lines were held and then dropped while nothing was heard.
- A number is read as an ordinal where only an ordinal fits: «с 15 уровня» — «с пятнадцатого уровня», «на 2 этаже» — «на втором этаже», «15 уровень» — «пятнадцатый уровень». With words that number rather than count (level, floor, place, rank, phase, season, chapter, act, wave, slot, boss) also «с 21 уровня» — «с двадцать первого» and «хил 15 уровня» — «пятнадцатого». Counts stay counts: «200 опыта», «на 2 уровня выше», «5 раз».
- «Число» as a date is a word that numbers: «до 11 числа» — «до одиннадцатого ч+исла». After an ordinal, «числа» and «места» get the singular's stress: the stress model always took them for the plural («числ+а», «мест+а»).
- The dictionary reads «аук» in every case as «аукцион» («на ауке» — «на аукционе»), and the Ragefire Chasm typed in full as «Огненная пр+опасть», not with the verb's stress «пропа́сть», in the case its preposition asks for («в Огненная Пропасть» — «в Огненную пропасть»).
- The dictionary reads «танчить» as «т+анчить» in every form, and «МСК» as «эм-эс-к+а».
- The chat no longer talks over CatQuest: while CatQuest reads a quest, chat lines wait and are read once it is done (lines that waited over 40 seconds are skipped); a setting, on by default. The quest is not paused for the chat instead: the game cannot resume a sound in the middle, so the quest would start over after every chat line.
- When CatQuest starts speaking while a chat line is being read, the chat stops at once and waits; once CatQuest is silent, the line it cut is read again from its start, then the rest. A pause whose end never reaches the program ends by itself after 90 seconds.
- Quest and item links read as their names: no brackets, no quest level tag ("[24]"), and the word before a link no longer runs into it.
- Words in capitals («РАЗЫСКИВАЕТСЯ», «ВСЁ», «СТОЙ») are read as words, not as abbreviations with the stress in the wrong place; an abbreviation the dictionary does not know is read letter by letter when it cannot be said as syllables, as in Russian speech: «ППС» — «пэ-пэ-эс», «ЦРУ», «США», and a syllable it begins with is said as one: «ГИБДД» — «ги-бэ-дэ-дэ»; «ОМОН» or «ВУЗ» are read as words.
- Swear words hidden from the chat filter are read as the words they are: a bracket pair for "х" ("на)(уя"; it used to become a full stop), Latin look-alike letters ("xyйня"), a digit inside a word ("п0шел") and asterisks for letters ("бл*ть").
- `assignments.json` (which voice each character has) no longer grows without end on a busy server: characters not heard for 60 days are forgotten (one who comes back gets a voice again, the same one when there are voices to go round), and the file is written every 30 seconds and on exit instead of on every chat line.
- Races without voices of their own in the client speak as their kin: goblins and vulpera as gnomes, blood elves as night elves, and so on. If you pinned a race voice to a player in `players`, the voice names changed (`orc-male/standard` and the like).

## 0.1.0

- Initial release.
