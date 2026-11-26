# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> MAJOR is still 0 ([spec item 4](https://semver.org/spec/v2.0.0.html#spec-item-4)): MINOR carries everything that is not purely a fix — new features and BREAKING changes alike — and PATCH is fixes and docs only (0.2.1 predates this rule and added features too). Every breaking change is titled `BREAKING:` — a name, a command, a file or a setting that no longer works as it did — so `grep BREAKING` over this file lists them all.
>
> Release dates are the GitHub release's publication date (UTC). Versions before 0.4.0 had no GitHub release: their date is the release commit's, and their tags were set later on those commits.

## [0.6.0] - Unreleased

### Added

- The installer puts the addon into the games

  After installing, a page «Аддон в игры» lists the World of Warcraft clients found (Forever and retail, found as the launcher finds them), each with its folder and the addon there, every box ticked (retail's marked «ритейл мало тестировался»). Next installs the addon into the ticked ones; one that fails is said, with the launcher's «установить аддон» to try again. No game found, or a silent install: no page.

- The log says how soon a line was heard, and `audio_wasapi` to try WASAPI

  With `log_details` each race voice line gets «до звука 0.83 с (MME, задержка выхода 120 мс)» under it: from the line's arrival to its first sound, and the output. `audio_wasapi` in config.json (off; not in the launcher's settings) plays through WASAPI's default output in shared mode instead of MME's sound mapper, and opens it for a moment before a line made after 5 s of silence — after the fork sokol-rc/barrens-voice, where that started the first line after a silence in 0.76 s instead of 8.6 s. A stream WASAPI refuses plays through MME; a change of Windows' default output is picked up before the next line.

- The installer takes the CUDA build only where it runs

  The CUDA build's libraries are CUDA 13: they need a driver for CUDA 13 (R580 or newer) and a GeForce 16, 20 or newer. The installer reads both from nvidia-smi (the CUDA version in its header; the driver's number when the header has none) right after Python is downloaded, before the libraries. A driver too old: it asks «Обновить драйвер NVIDIA?» - yes (the default) opens NVIDIA's driver page and stops, to be run again after the update; no installs the DirectML build (the game may stutter while a line is made). A card too old for CUDA 13: the DirectML build, said why. Before, any NVIDIA driver got the CUDA build, and an old one left the race voices off. A driver too old to know the card's compute capability is asked again without it. Updates keep the build an install was made with: an install that got CUDA on an old driver gets DirectML by running the installer again.

- The installer's steps on its own page, not in a console window

  «Скачиваю Python и библиотеки…» and «Скачиваю модели голосов…» each with the line it is at below (uv's, the program's), all of it in Setup's log. A step that fails asks to go again (what is downloaded is not downloaded again); a program not installed gets no addon page and no launcher, models not downloaded are fetched at the first start. Before, a failure left a console window paused.

- The sound device is checked at the start

  A tenth of a second of silence through the output when the program starts: a device that does not open is said then (the log, the launcher's yellow line), not at the first chat line.

- «Голоса рас: Качество · Баланс · Скорость» in the launcher's settings

  F5's steps a line (`f5_steps`): 10 (Качество, the default), 8 (Баланс) or 6 (Скорость), the number in each choice's hint. 8 and 6 are the same model with its step tables put on a coarser grid (after the fork sokol-rc/barrens-voice): a line is made about a fifth (8) or half again (6) sooner and the video card is freed sooner. With DirectML each step is one hitch of the game's frame, about 70 ms (up to 110) whatever the number of steps: 8 has a fifth fewer of them, 6 about 40 % fewer (measured with DirectML on an NVIDIA card and a stand-in for the game; with CUDA there are none), and the hints say so. By ear nearly the same; at 6 a stress was heard on the wrong syllable now and then (the dictionary's too) or a syllable blurred - the cause not checked yet. The rewritten model is made at the first choice (a couple of seconds) and kept in the cache, about 660 MB: another number replaces it, 10 removes it; a rewrite that fails falls back to 10, said in the log. Each choice's hint says what it brings. The program gets the `onnx` package for it.

### Changed

- Stresses: RUAccent reads a line in lower case

  RUAccent looks a homograph up in its table as written, and the table is in lower case: a word with a capital missed its context model and got one default stress («Прид+ержите моё пиво», «Посл+е пары банов», «Аллея Чест+и», «Песни В+ойны», «Кат+я»). Now it reads as the same word typed in lower case. On 2125 chat lines from the log, 14 words came out better and 4 worse; of those, «Степи» (the zone, so a real steppe too: «в широкой степи») and «Леса Ночной Песни» are now in the dictionary, with the other names from the game's tables RUAccent misreads in lower case («Глуб+ины Чёрной горы», «Келебрас Пр+оклятый», «Остров+а Эха», «Пол+я Великанов», «Пл+ети»), and «БРД» got its «Глуб+ины». The marks go back onto the text as written, so the speech gets the same letters.

- A race voice's line of several sentences starts sooner: its first part plays while the rest is made

  `f5_first_sentence` in config.json (on; not in the launcher's settings). The line is cut where it is made in parts anyway (a question after statements), else after its first sentence only when it and the rest have four words each: every extra piece costs F5 nearly a short line's work, so «привет) го в данж» stays whole. A short pause after the first part. `false`: the line made whole and played as one, as in 0.5.0.

- Dictionary

  «хуево» as «хуёво» in every form («хуевый», «хуёвина», «до хуев»): the «ё» list the program restores from has no swear words. «хуева туча» (a lot) stays «х+уева т+уча» in its forms, «хуевато» is «хуев+ато».

  «чекну» (check) as «ч+екну» in every form («чекни», «чекнул»), «чекать» as «ч+екать».

  «морока» as «мор+ока» in its five forms, not declined («без мороки»): RUAccent took it for «м+орок».

  «т.е.» as «то есть» (glued to the next word too: «т.е.я пас»), «емае» as «ёма+ё», not declined («о емае»).

### Fixed

- A race voice's long line is made in pieces of up to 15 seconds

  F5 made a line's every part in one go, its reference voice included, and it was taught on clips of up to 30 seconds (upstream cuts at 22 with the reference): a long trade offer came out blurred at its end, at 6 and at 8 steps - its length the likely cause, not yet checked by ear. A part longer than `f5_part_seconds` (config.json, 15 seconds, at least 5) is now cut where a speaker pauses - at sentence ends, else at commas and dashes, between words into runs of about equal length only for a clause still too long, not after «и», «не», «в» -, each piece made on its own with a short pause between; a short sentence before a long one goes with its head; a dash ending a piece is read as a comma; the next piece is made while one plays.

- A word in capitals that a dictionary stem takes has its ending in lower case too

  «ХУЕВО» was «хуёвО», «БУРГЕРЫ» «б+ургерЫ» - a capital inside a word: the stem's replacement is lower case, the ending was kept as typed.

## [0.5.0] - 2026-11-23

### Added

- Smileys as words

  «и смайлики» under «Озвучивать имена» (on by default): a line of nothing but smileys is read as an emote — «)))», «:D», «xD» «Громмаш смеётся»; «)», «))», «:)», «8)», «:3», «^_^» «улыбается»; «(((», «:(» «грустит»; «T_T» «плачет»; «O_o» «удивляется»; «-_-» «хмурится»; «>_<» «морщится»; «<3» «показывает сердечко»; «=\», «:/» «в недоумении».

  At the end of a line the same feeling follows it, the smileys themselves not read out («<3» at the end is no longer «три»): two brackets for a smile or sadness, three for a laugh («И улыбается.», «И смеётся.»). One bracket or «:)» after a phrase stays the pause it was; a smile someone took the trouble to type («^_^», «:3», «8-)», not a quick «^^») is said («И улыбается.»).

  Not smileys: «8)» after a word is left as typed (it may be «в 8»), spaced brackets that pair up («( это шутка )») stay parentheses, faces mid-line («^_^», «T_T», «O_o», «-_-», «>_<») are a pause and count as whole words only («leo_orc», «10_000» stay), and a line of smileys names no place. Chosen from the chat's own logs: brackets and letters, no picture emoji.

- The volume by the mouse wheel over the minimap button

  A notch is 5 %, as the game's own volume sliders, within the slider's 0–200 %; the button's tooltip shows the volume, and the slider on «Общее» follows. The line already playing follows at once, louder and quieter: the launcher now plays a line as a stream (`sounddevice`, PortAudio) and applies the volume to every block of it, instead of a file through `winsound` at a volume fixed when it was made. The stream goes through Windows' sound mapper, as `winsound` did, so it follows the default output: headphones plugged in or out, a stream that fails or stalls is opened again on the list of devices read afresh and goes on from where it stopped. With no device at all the launcher's window says «звук не играет…» in yellow, and the next line tries again.

- The race voices' clips chosen by ear: a voice lab and `voice_picks.yaml`

  `python -m bv --voicelab <folder>` puts every line of every race voice from the client into its folder (`all/`), the lines its reference clip is made of (`used/`), the clip and a test line F5 speaks with it, and `voices.yaml` listing them all, the used ones uncommented: edit it and run again to hear the result. Carried to `companion/bv/voice_picks.yaml` (`-- --pick`: only the voices chosen otherwise than automatically, or with a text corrected), a voice listed there takes exactly those lines (an empty list drops the voice), each with its text from the file - the same on every machine, correctable by hand, no Whisper for it; the others are chosen as before. The picks of the game's own voices are part of the bank's stamp: once there are any, the race voices are collected again once, after the update that brings them; an empty file changes nothing.

- The CurseForge and Wago apps recognise the addon the launcher installed

  The addon's TOC names its projects (`X-Curse-Project-ID`, `X-Wago-ID`); the release workflow checks they are the repository's variables. A test build's addon goes without them: the sites have releases only.

### Changed

- Parentheses are read with a short pause either side

  «танк (опытный) нужен» is said «танк, опытный, нужен»; a line in parentheses has no pause at its ends. A lone bracket is still a smiley's pause, brackets inside a word («бл(и)н») go and the word is read, and a quest's number in its link («(3513)]») is still dropped.

- The addon's description in the game's addon list says what it does and that it needs Barrens Voice Launcher for Windows

  «Озвучка чата: у каждого игрока свой голос — голоса рас или голоса Windows. Нужна программа Barrens Voice Launcher для Windows.» Not «приложение-компаньон», without «F5-TTS» and without the strip, which the README and the welcome explain.

- «РЛ» and «БР» are read letter by letter

  «РЛ» is «эр-эл» wherever it stands, its ending as typed («РЛу» «эр-элу»), in agreement with a number («2 РЛ» «два эр-эла»), not declined after a preposition («к РЛ» «к эр-эл»): it was the Ruins of Lordaeron or the raid leader by the words around it, and often the wrong one («у РЛ спроси», «РЛ кинул инвайт»). «БР» is «бэ-эр» («есть 2 бр» «два бэ-эра»), not «боевое воскрешение» («бр, холодно»). A player's own edits of the plain, the endings' and the number's «РЛ» rules and of the word «бр» keep working; the two rules that read «РЛ» by the words around it are gone.

- Dictionary

  «форевер» (WoW Forever) as «фор+евер», «Гномреган» as «гномрег+ан», «бургер» as «б+ургер» in every form, «суманем» (summon) as «суман+ём», «стакается» (stacks) as «ст+акается», «качается» (levels up) as «кач+ается», «глобал» (the global channel) as «гл+обал», «димоны» as «д+имоны» (the plural only: «Димон» is a name), «новичек» as «новичёк», «Ониксия» as «он+иксия» in every form, «оня», «онька» as «Он+иксия» instead of «Логово Ониксии», «оню», «оньку» as «Он+иксию», «оне» («на оне») as «Он+иксии», «Ростов-на-Дону» as «Ростов-на-Дон+у».

  The greetings «дарова», «здарова», «даров», «дарово», «здаров», «здарово», «дароу», «здароу» with the stress on the «о» after «р» («дар+ова», «здар+ово»), not declined after «о,».

  The addon and its sites typed in Latin: «barrens voice», «curse forge», «wago» as «Б+эрренс В+ойс», «К+ёрс Ф+ордж», «В+аго», not declined.

  «баф» («бафает», «бафнул», «бафы», «дебаф», «ребаф», «ребафни») with the stress on «а» («Бафомет» on «е»).

### Fixed

- A whisper, guild or group line held while CatQuest or Wayfarer speaks shows its chat window again when it is read

  With «Показывать при шёпоте / строке гильдии / группы» on, the window showed as the line came and faded 10 s later, while the line waited for the quest voice-over (up to 40 s; longer, it is dropped) and was read with no window in sight. The addon holds such lines itself, so it knows when one goes to be read: the window that showed it shows again then. A line the program was already reading when the quest voice-over cut it in is read again after it without a second window.

- «Озвучить» in the dictionary window reads with the player's own name and voice

  It sent the character's name alone (on Forever without the surname «и фамилии» adds), so the line got another voice than the player's own chat lines. It now goes as the sender the chat gives the player's own lines, the name alone until the character has written one.

- A tester moving from the test builds to the release sees the release's «Что нового» once

  Every test build showed the release's entry and marked it seen, so the release, whose entry is rewritten for it, showed nothing. The first login on a release after its test builds shows its entry again, as the window for a big one; players from an earlier release and newcomers are unaffected.

## [0.4.0] - 2026-11-21

The first public release, and the first on GitHub: an installer, updates by themselves and a launcher window instead of a console, under a new name.

### Added

- Installer

  `BarrensVoice-Setup.exe` installs for the current Windows user without administrator rights (by default into `%LOCALAPPDATA%\BarrensVoice`): the program, Python and its libraries through uv (the CUDA build with an NVIDIA card, DirectML otherwise) and the models — about 6 GB with NVIDIA, 4 GB otherwise. Uninstalling asks whether to delete the settings, the voice bank and the models too.

- Automatic updates

  The launcher checks GitHub Releases at start and hourly, trusts a release only with its signed manifest (ed25519), prepares the new version beside the current one and switches when the game and the voice-over are not running, or at once on «Установить сейчас». A version that fails to start is rolled back and not taken again by itself. «Получать тестовые версии» takes the test builds (tag `v0.4.0-beta.5` is version `0.4.0b5`). The addon follows: an older one is replaced in each game that is not running, a newer one (from CurseForge, say) stays.

- Barrens Voice Launcher window instead of the companion's console

  The state of the voice-over, the game, the race voices and the link with the addon; the log, and «Журнал» with levels, search and «Копировать для отчёта»; the installed games with «установить аддон» / «обновить аддон»; «Играть»; settings with a folder per game (`game_dirs`); the start with Windows and waiting in the tray; «Помощь».

- The dictionary online

  CI publishes the default dictionary, signed, after the tests pass on master (branch `dictionary`); the launcher fetches it at start and hourly and uses it while it is newer than the addon's own, so words reach players without an addon update. `dictionary_online` in config.json turns it off.

- «Что нового»

  After an update, a few seconds after login and never in combat, a window with every release's entry in the players' words (or just a chat line for a release of fixes); `/bv news` and a button on «Помощь» open it any time, and «Окно «Что нового» после обновлений» leaves only the line. The entries live in `news.toml`, and the GitHub release's description is the same entry.

- «Помощь» in the addon's settings and the launcher

  Barrens Voice's community in Battle.net (opened in the game itself), Discord, Telegram and GitHub issues, each to copy or open.

- Where a line was said

  «Громмаш пишет в гильдии: …», «пишет в торговлю», «объявляет рейду»; said only when the place changes or after 30 s of quiet (on by default, under the names).

- «Что читать»

  Every channel on (also those no chat window shows), what the chat windows show (as before, the default), or only the selected chat tab, whisper tabs included.

- Battle.net whispers are read

  A friend in WoW by their character's name and race voice, otherwise by the BattleTag without its digits. The account's real name is never said or logged.

- One's own whispers are read with «Свои сообщения», in one's own voice, without the name of the one whispered to
- The hidden chat shows on group lines («при строке группы/рейда», on by default)

  «при шёпоте» and «при строке гильдии» are on by default now too: such lines are easy to miss by ear.

- A dictionary replacement can stay as written

  One starting with «!» is not declined after a preposition («скачки=!ск+ачки»).

- «Отладка» under «Дополнительно» in the addon's settings, as `/bv debug`
- A strip of another protocol is told apart from a covered one, with which side to update

  Lines skipped under a strip another addon partly covers are told in the log, with where to move ours.

- The hidden chat's `/reload`

  A launcher started after login says the hidden chat needs one, in the log and as a tray notice.

- Whisper can judge a line's ending

  Before a line is made again for its cut ending, Whisper listens whether the last word is heard (`f5_end_check: "whisper"`, about 1.5 GB of video memory; `"silence"` by default).

### Changed

- BREAKING: the mod is called Barrens Voice

  The addon's folder is `BarrensVoice`, its command `/bv`, its saved settings `BarrensVoiceDB`; the companion's package is `bv`. Nothing carries over from WoW Chat Voice by itself.

- BREAKING: the race voices run on ONNX Runtime instead of torch

  F5 and Whisper in ONNX: CUDA on NVIDIA, DirectML on any other DirectX 12 card (the game may stutter there while a line is made); a session put on the processor is refused and the chat is read with Windows voices. The Python environment is 2.8 GB with CUDA or 0.6 GB with DirectML instead of 6.4 GB. `requirements-f5.txt` and `nfe_step` are gone.

- BREAKING: the voice-over always ends with the game

  It frees the video memory; `exit_with_wow` («Закрываться вместе с игрой») now says whether the launcher closes too or waits for the next game.

- The program is called Barrens Voice Launcher («лаунчер»), what reads aloud in it «озвучка»

  The mod speaks to the player with «ты».

- The chat waits for NPC lines CatQuest and Wayfarer voice (a herald, a mob in a fight), as for quests

  The setting is «Ждать озвучку CatQuest/Wayfarer».

- The addon's word at login (whether the voice-over works) and the first run's welcome come 5 s after login, below other addons' lines

  Every addon line starts with its icon; long tooltips are in paragraphs.

- The strip is at the bottom edge by default
- The transparent chat fades only when the launcher ran at login or the last `/reload`

  Lines nobody reads would be lost.

- «Перераздать голоса» is `/bv reset-voices`
- A raid warning is «объявляет»

- The dictionary window keeps a line where it was typed

  It is sorted when the window shows again.

- On retail the «Каналы и чтение» tab says that dungeons, raids, boss fights, Mythic+ and PvP close the chat to addons

  CatQuest and Wayfarer (Forever's addons) are left out.

- Dictionary

  «95%», «кача», «рога», «рмт», «ЛИ», «пздц», «импрувед», «лк», «бк», «дс» (Discord), «спек», «<3» at a line's end (a smiley), «бтв», «скрафтить», «вендор», «нп», «скачки», «ниче», «темп», «лвл» in every case, «х2», «х3», «+-», «2х2», «2г50с», «см» after a number, years with «г».

### Removed

- BREAKING: `WowChatVoice-Retail.cmd`

  The game is chosen in the launcher's window, or with `--retail`.

### Fixed

- Numbers are read as meant

  Counts after prepositions of the genitive («у пяти игроков», «до пяти утра»), ordinals where they belong («с первого по пятый уровень», «на 4м этаже» — «на четвёртом»), ranges and dates («до двух-трёх человек», «до пятого мая»), years («в 2026 году»), times («20:00», «20-00»), «+» after a number («18+» — «восемнадцать плюс»), and thousands, gold and seconds after a number («10к хп» — «десять тысяч здоровья», «+5 к силе», «100г», «2 кк», «кд 30 с»).

- Units after a number are not taken for a preposition («5с кд», «10к хп»), and slang the declension knew only as a place name is not declined («для кача»)
- Spelt abbreviations keep their stress on a vowel («эм-вэ-д+э»)

  Windows voices read the «+» aloud.

- Discord's emoji codes, «*да*» and «@Вася» are not read out or unmasked into swear words, and «Лок'тар огар!» is not a dictionary entry
- A space between the speaker's name and the line («Вася пишет: привет», not «пишет:привет»)

- A character from another realm is named without the realm, and keeps their voice
- «спрашивает» for questions with «р», «Ц», «—» or «№»

- Lines another addon's chat filter hides are not read on Forever
- The hidden chat goes by the line each window shows, gives the edit box back its own alpha, and leaves retail's frames with a secret name alone

- Nothing stale after `/bv on`

  No old test lines or links, and lines held for a quest voice-over are dropped at `/bv off`.

- The dictionary window

  «Озвучить» right after an edit uses it, a typed «|» stays one «|», a line over 480 bytes is said, not sent cut.

- The strip

  A frame drawn from one edge while it moves, found at once after a restart mid-game, «полоска видна, но не читается» cleared when it reads again.

- Lines under another addon's strip (wow-ai) are no longer lost without a word
- The race voices

  An empty voice bank is an error, not silence; a failed load is not retried on every line; a damaged bank is made again; a Windows voice sample no longer unloads them; a very short question is read; a RUAccent download cut short is fetched again.

- The companion

  A line that fails to play no longer silences it, lines play again after the temporary folder is cleaned, a locked `VoiceList.lua` or a failing screen grab no longer stops it, and once it has stopped the addon no longer says at login that the voice-over works.

- config.json

  A file that does not parse is said in words and never written over, impossible values are replaced with a warning, a file with a BOM is read, `_help` is this version's.

- The game

  Only `Wow.exe` in a game's folder is the game (not WowUp), no second game is started, and the launch command is sent again when Battle.net was not running.

## [0.3.0] - 2026-11-15

### Added

- Retail WoW

  `WowChatVoice-Retail.cmd` (or `"game": "retail"`) for retail's folder, with a voice bank of its own; files retail has not downloaded yet are taken from an installed Forever.

- Retail's races speak with their own voices from the game's voice-over

  A race the client lacks speaks as its kin.

- Retail's closed chat (dungeons, raids, boss fights, Mythic+, PvP) is left alone without errors, and the addon says so once
- Skyborne speak with their own voices

- The chat waits for Wayfarer as for CatQuest
- The chat windows can stay out of sight while the mouse is not over them («Прятать окно чата»)

  A line not read aloud shows its window for 10 seconds.

- A box for each numbered channel

  General without Trade, say.

- Where to get more Windows voices

  RHVoice and Silero, opened in the browser.

- The chat says at login whether the reading works
- A welcome on the first run

- Other addons' messages are not read (Questie, DBM, BigWigs, Details!)
- «спрашивает» for a line of questions

- «ё» restored where only «ё» can be meant («ждём», «ещё»), `restore_yo` turns it off
- Library warnings in the companion's log, marked `[stderr]`

### Changed

- The settings window is in the game's own tabs

  «Общее», «Каналы и чтение», «Голоса», «Словарь».

- Everything on «Каналы и чтение» is on by default
- The speed and volume sliders' 100 % is the default sound

  Saved settings are converted once.

- The program learns where the strip is from the addon, and finds it anywhere in the window failing that
- One model cache (`hf_home`) for every model

- Dictionary

  «тг», «ага», «чиловая», «тикет», «хелло», «менеджмент», «др», «чето», «берёт», «ружьё», «РЛ» (Ruins of Lordaeron, or the raid leader where the words around say so), hyphenated words declined as one.

- «1 место» is a count («одно место»)

  «15 место» stays an ordinal.

### Removed

- BREAKING: `/wcv reset`

  The «Перераздать голоса» button does it.

- BREAKING: «Склонять замены после предлогов» and «Только то, что видно в окнах чата» are no longer settings

  Both are always on.

### Fixed

- `/wcv last` no longer loses lines, and remembers the last 50 over `/reload` and a restart

- The companion stops when the addon is not installed, saying where it looked
- The race voices option no longer says they come from CatQuest

## [0.2.1] - 2026-11-12

### Added

- One speech per character

  Several lines in a row from one character are read with the name only before the first.

- Where the strip is can be set

  The top edge, the bottom edge or a place of one's own, so another addon (wow-ai) does not cover it.

- `/wcv debug`

  Why a chat line is not read, in the program's log.

- Dropped lines are noted in the program's log
- Ordinals where only an ordinal fits

  «с 15 уровня» — «с пятнадцатого уровня», «на 2 этаже» — «на втором этаже».

### Changed

- The dictionary is applied by the program, which picks up a change without `/reload`

  A character's name is no longer run through it.

- CatQuest cuts in

  The chat stops at once and reads the cut line again from its start.

- Dictionary

  «че», «серега», «пикабу», «PvE», «аук», «Огненная пропасть», «танчить», «МСК», «кв», «шт».

### Fixed

- The chat no longer waits for a stuck CatQuest

- Item links and a colon before a Russian letter no longer garble the speech
- The strip is drawn above the rest of the interface

- The strip is as thick as the longest line needs
- A quest's number after its name is not read out

## [0.2.0] - 2026-11-11

### Added

- BREAKING: race voices come from the game client itself

  The Russian voice-over of the playable races, the character's voice and NPC voices, each also lower and higher; CatQuest is no longer needed. Voice names in `players` changed.

- The chat waits for CatQuest while it reads a quest
- Hidden swear words are read as the words they are

### Changed

- Slow voices speak faster, and each character at a tempo of their own

- The race voices load while the game starts
- Quest and item links read as their names

- Words in capitals are read as words

  Unknown abbreviations letter by letter.

- `assignments.json` forgets characters not heard for 60 days
- Dictionary

  Discord, «перекрёсток», «поножи», «ПС».

### Fixed

- Endings no longer get cut off

- Very high and very low voices no longer rasp in questions
- Numbers get their stress like other words

- A word the stress model splits keeps the line's other stresses
- A dictionary stem keeps the case typed in chat

## [0.1.0] - 2026-11-11

### Added

- The first release

  The addon sends the chat to a companion program on Windows, which reads it aloud with a voice of its own for every player — race voices (F5-TTS) or Windows voices — and a slang dictionary («WTS» — «продам», «дд» — «дамагер»).

[0.6.0]: https://github.com/rgeraskin/barrens-voice/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/rgeraskin/barrens-voice/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/rgeraskin/barrens-voice/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/rgeraskin/barrens-voice/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/rgeraskin/barrens-voice/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/rgeraskin/barrens-voice/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/rgeraskin/barrens-voice/releases/tag/v0.1.0
