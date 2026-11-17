# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> MAJOR is still 0 ([spec item 4](https://semver.org/spec/v2.0.0.html#spec-item-4)): MINOR carries everything that is not purely a fix — new features and BREAKING changes alike — and PATCH is fixes and docs only (0.2.1 predates this rule and added features too). Every breaking change is titled `BREAKING:` — a name, a command, a file or a setting that no longer works as it did — so `grep BREAKING` over this file lists them all.
>
> Release dates are the GitHub release's publication date (UTC). Versions before 0.4.0 had no GitHub release: their date is the release commit's, and their tags were set later on those commits.

## [0.4.0] - Unreleased

### Added

- An installer

  `BarrensVoice-Setup.exe` from the latest GitHub release installs for the current Windows user, without administrator rights, into one folder (by default `%LOCALAPPDATA%\BarrensVoice`): the program, `data` (settings, the voice bank, logs) and `cache` (models). While installing it downloads Python and the libraries through uv — the CUDA build with an NVIDIA card, DirectML otherwise — and the models (~3 GB): about 6 GB on disk with NVIDIA, 4 GB otherwise. The folder has «Barrens Voice.exe» with the app's icon, which starts the current version; the shortcuts and the start at Windows sign-in go through it. Uninstalling stops it and asks whether to delete the settings, the voice bank and the models too. `BarrensVoice.cmd` stays for running from the source, and downloads the models too (`python -m bv --fetch-models`).

- Updates by themselves

  An installed Barrens Voice checks GitHub Releases at start and hourly and trusts a release only with its signed manifest (ed25519) and an archive that matches it. With «Обновлять автоматически» (on by default) the launcher downloads the new version and builds it beside the current one in the background, with the uv the release names, and switches to it when the game and the voice-over are not running — or at once on «Установить сейчас»: the voice-over stops for about half a minute while the launcher restarts into the new version and starts it again for the running game. With the check off, the notice offers «Обновить». A failed download or build is tried again at the next check; a version whose companion fails right at start twice is rolled back. Windows «Apps» shows the version in use. The notice says «Вышла версия 0.4.1 и аддон 0.3.2» (the addon only when it changed), under it what the update does («обновление скачивается… / готовится… / ждёт закрытия игры»), and «Что нового» opens the release's page. The addon follows the app: with automatic updates an older addon is replaced in each game that is not running (a newer one, from CurseForge, stays); otherwise a game's card offers «обновить аддон». «Получать тестовые версии» takes pre-releases: a test build carries its own version (tag `v0.4.0-beta.5` → `0.4.0b5`, shown as «0.4.0 beta 5»), a newer beta is an update, and the release is newer than its betas. The app's version is `pyproject.toml`'s now, the addon's its own.

- A launcher window instead of the companion's console

  `BarrensVoice.pyw` opens a window: the state (companion, game, race voices with the video card, the link with the addon), the companion's log, the start options with hints (launch the game with Barrens Voice — off by default; close with the game; start at Windows sign-in, then waiting in the tray), the installed games with the addon's version in each and «установить аддон» / «обновить аддон», «Играть», settings, help and the update notice. Opened by hand it starts the companion only with the game — when the game runs or appears, on «Играть», or with «Запускать игру» on — so the race voices take video memory only for a game. The cross closes it with the companion (asking if the game runs); it hides in the tray by itself when it starts the game and at Windows sign-in; when the launcher ends, the companion ends too. The games are found where they last ran, from the registry and Battle.net's settings, and in the usual folders on every local disk; the settings have a folder field for each game, «Папка WoW Forever» and «Папка WoW Retail» (`game_dirs` in config.json; the single `wow_dir` is still read), ask whether to save changes when closed, and link to the description of config.json. The log says at once when the chosen game has no addon. Installing the addon mirrors it into the game: files the new version no longer has are removed, the two the companion writes there (`VoiceList.lua`, `CompanionStatus.lua`) are kept; with the game running a `/reload` is enough (checked on Forever's client, new files and pictures included). The window follows the Windows screen scale; its icon is the addon's. `BarrensVoice.pyw` and `BarrensVoice.cmd` take the same switches (`--retail`, `--console`, `--f5`…, `--help`).

- Log levels

  Every line of the companion's log carries one — DEBUG, CHAT, INFO, WARN, ERROR — decided by the message in one table (`bv/logs.py`). The launcher's main window shows only how things go (INFO and up, without the level), in plain words and lines written to fit (one that does not wraps under its time; the details are in the full log, indented), and a long job as one line that moves on. «Журнал» opens the full log live, with filters by level, search, «Копировать» (the selection, or every line the filters show), «Копировать для отчёта» (the version, Windows, the ONNX Runtime build, the video cards, the race voices' state, the games with their addon and the settings changed from the defaults — folders, the WoW account and players' names left out, the home folder as `~` — then the last 300 lines of every level) and scrolling that follows new lines only while at the bottom. What libraries write below Python (onnxruntime, progress bars) comes as `DEBUG [stderr]` lines of its own.

- The voice bank's progress in the log

  Building the bank (once, and after each game update) logs «собираю голоса рас: N из M» every 10 seconds, then «голоса рас собраны: N из M за X мин»; the launcher's main window keeps them in one line that moves on.

- Whisper can check a line's ending

  A line whose speech runs to the very end of its length (about one in eight) is made again with more length, as before; the launcher's settings can instead have Whisper listen to its ending first and make it again only when the last word is not heard (`f5_end_check`: `"silence"` by default, `"whisper"` saves a second on such lines for about 1.5 GB of video memory).

- A strip of another protocol is told apart

  A strip whose protocol the companion does not read is not taken for a covered one («полоска видна, но не читается»): after 3 seconds the companion says which to update — «аддон новее Barrens Voice — обновите Barrens Voice» or «аддон старше… — «обновить аддон», потом /reload» — and the launcher's «Мост» line says so. A new protocol keeps reading the one before (`protocol.SUPPORTED`).

- The hidden chat says it needs a `/reload`

  A companion started after the player entered the world says that the hidden chat needs a `/reload`, in the log and as a tray notice. It asks before its first beat (`bv/reloadhint.py`): «Прятать окно чата» on and the addon not switched off in its saved settings, no companion running a moment ago (a restart by the launcher — the addon saw that one), and the strip already on screen.

- A «Помощь» tab in the settings

  Where to write about bugs, ideas and words read wrong — Discord, Telegram and the GitHub issues, each with its icon, its address in a box (a click selects it, Ctrl+C copies), «Копировать» and «Открыть». The game gives an addon neither the browser nor the clipboard, so the companion does both (bridge kinds `open` and `copy`, only for the addresses it knows). The welcome on the first run and the line after an update point to it.

- «Отладка (/bv debug)» in the addon's settings

  Under «Дополнительно», with a tooltip on what it writes and why to keep it off otherwise.

### Changed

- BREAKING: the mod is called Barrens Voice

  After the Barrens chat. The addon's folder is `BarrensVoice`, its command `/bv`, its saved settings `BarrensVoiceDB`; the companion starts with `BarrensVoice.cmd`, its Python package is `bv`, its logs `bv-YYYY-MM-DD.log`. Nothing carries over from the old names by itself.

- BREAKING: the race voices run through ONNX Runtime instead of torch

  F5 exported to ONNX (DakeQQ/F5-TTS-ONNX, 10 steps; the models from Hugging Face `rgeraskin/barrens-voice-f5-onnx` into `models\f5-onnx`, `f5_onnx_dir`) and Whisper large-v3-turbo in ONNX for building the voice bank. On NVIDIA they run with CUDA (`onnxruntime-gpu`), and the game does not stutter while chat is read; on any other DirectX 12 card with DirectML, which holds the video card for each whole denoising step (~100 ms), so the game stutters while a line is made. The companion takes CUDA, then DirectML, and refuses a session ONNX Runtime quietly put on the processor instead (DirectML without DirectX 12): the race voices fall back to Windows voices at once, without building the voice bank for nothing. Every ONNX session gets two threads that sleep when idle, and the companion runs below normal priority (`share_with_game`, `onnx_threads`). The Python environment is 2.8 GB with CUDA or 0.6 GB with DirectML instead of 6.4 GB; a line takes about 1.1 s on an RTX 5070 Ti, as with torch. The models are downloaded while installing, not at the first start; what fails to download, the first start downloads. `requirements-f5.txt` and the `nfe_step` setting are gone, the library versions are pinned. RUAccent keeps its dictionary and models (`koziev` among them) in the model cache (`hf_home`, folder `ruaccent`), so a new Python environment needs no download. The voice-type tooltip in the addon says «DirectX 12» instead of «NVIDIA».

- The strip is at the bottom edge by default

  «Внизу (обычно)» in «Мост к компаньону…» (it was the top). An addon with saved settings keeps its place.

- The transparent chat fades only with the companion running

  Only while the companion was running at login or the last `/reload`: hidden lines nobody reads would be lost. A companion started later makes it transparent at the next `/reload`.

- «Перераздать голоса» is a command now

  `/bv reset-voices` (it asks first, as the button did): handing the race voices out afresh is rarely needed, and «Общее» has the main switch and «Проверка» across its width.

- The links to more Windows voices are rows

  RHVoice and Silero on «Голоса» are rows of the same kind as on «Помощь»: the address to see and copy, «Копировать» and «Открыть».

- Dictionary

  «95%» is read «95 процентов» (1 процент, 2 процента), «кача» as «к+ача», «ЛИ» (in capitals only: «ли» is a particle) as «Лабиринты Иглошкурых», «пздц» as «пиздец».

- Library notices left out of the model download

  The model cache's warning about symlinks on Windows (it keeps plain copies without developer mode, which costs nothing here) and two of RUAccent's own notices (a regex string without `r""`, an argument huggingface_hub ignores) are no longer shown.

### Removed

- BREAKING: `WowChatVoice-Retail.cmd`

  The game is chosen in the launcher's window, or with `--retail`.

### Fixed

- Starting the game when Battle.net is not running

  Battle.net drops the launch command while it starts and logs in, so the game did not start. The command is sent once more when its window is up (or after a minute) — only once: a second one may start a second game.

- A space between the speaker's name and the line

  «Вася пишет:привет» in the log and to the synthesis, and an emote said «Васясмеётся»: `text.plain` stripped the line's leading space. `protocol.with_name` joins them with one.

- «Компаньон не запущен» after the companion stops

  A companion that stops (closed, crashed, ended by the launcher) marks its status file so: an addon loading after that says the companion is not running instead of «озвучка чата работает» from a beat of its last seconds.

- «полоска видна, но не читается» is cleared

  When the strip reads again («полоска снова читается») or goes away: a second cover in the same session was not logged.

## [0.3.0] - 2026-11-15

### Added

- Retail WoW

  The companion works with one chosen game: `WowChatVoice-Retail.cmd` (or `"game": "retail"`) starts it for retail — retail's folder, Battle.net's «WoW», a voice bank of its own (`voices-retail`). Voice files retail has not downloaded yet are taken from an installed WoW Forever: the same content keys, the same files. The addon's TOC lists both games' interface versions.

- Retail's races speak with their own voices

  From the game's Russian voice-over (the character's voice, three variants per sex): blood elves, draenei, goblins, worgen (and in human form), pandaren, dracthyr (and in dragon form), the allied races, earthen and haranir. A race whose recordings the client lacks speaks as its kin. Forever's bank keeps only Forever's races. A bank made while voice files were on no disk yet (retail is playable before Battle.net has downloaded all of it) is made again once the game's storage has grown by 100 MB; a complete bank never is.

- Retail's secret chat is left alone

  Retail closes chat to addons in dungeons, raids, boss fights, Mythic+ and PvP (text, sender and GUID come as secret values): such lines are not read and no error is raised; the addon says so once, and the hidden chat window shows them.

- Skyborne speak with their own voices

  Forever's own race (небеснорождённые) gets the character's voice, three variants per sex, from the game's Russian voice-over instead of human ones. The voice bank is rebuilt once, a few minutes before the next game start.

- The chat waits for Wayfarer

  As for CatQuest: Wayfarer's (WayfarerRU) quests, NPC lines, place lore and radio stories pause the chat, a paused Wayfarer does not. One setting for both: «Ждать озвучку квестов (CatQuest, Wayfarer)».

- The chat windows can stay out of sight

  «Прятать окно чата, пока на нём нет мыши» (off by default): the chat is read aloud anyway, so the windows — text, background, tabs, edit box — are transparent until the mouse is over them or you type. A line the program does not read aloud (a system message, loot, a channel switched off, your own line, an addon's message) shows its window for 10 seconds; only lines in the tab on screen do. The mouse over the chat counts only when no other window lies over it there. A whisper or a guild line can show the window though it is read aloud, if asked («Показывать при шёпоте», «Показывать при строке гильдии», off by default).

- A box for each numbered channel

  Under «Общие каналы»: General, Trade, Looking for group, Defense and the others — to read General and not Trade, say. All are on by default, so nothing changes until you switch one off.

- Where to get more Windows voices

  The settings say plainly that Windows voices sound mechanical and need installing for variety (Windows has only Irina), and are kept just in case: when race voices lag or do not run on the computer. Buttons «Скачать дополнительные голоса можно, например, здесь: RHVoice, Silero»: the companion opens the voices' download page in the browser (bridge kind `open`, only pages of its own list).

- The chat says at login whether the reading works

  «озвучка чата работает», or that the companion app is not running and the chat is read as soon as it is started. The companion notes the time in a file in the addon's folder every 15 seconds, and the game reads it at login and `/reload` (not during play); the settings show it too.

- A welcome on the first run

  What the addon is, that the companion app does the reading, where the settings are. After an update, one line on what is new.

- Other addons' messages are not read

  Lines other players' addons write into the chat for them — Questie's party progress («{звезда} Questie: … 1/1»), DBM, BigWigs, Details! and others — are skipped («Не читать сообщения аддонов», on by default): with Questie on two players in a group each progress line was read twice.

- «спрашивает» for a question

  A line that is nothing but questions is announced «Громмаш спрашивает: …» instead of «пишет» (the voices raise their tone at a question mark unevenly, the verb tells it by ear); yells and whispers keep their verbs.

- «ё» restored where only «ё» can be meant

  «ждем» → «ждём», «еще» → «ещё», «утес» → «утёс»: the safe dictionary of eyo-kernel (MIT, about 107 thousand word forms); «все»/«всё» and the like stay as typed. `restore_yo` in config.json turns it off. RUAccent never put «ё» itself.

- Library warnings in the companion's log

  Warnings and errors the libraries write to stderr (torch, transformers) go into the companion's log file too, marked `[stderr]`; their routine notices at start and while the voice bank is built (the deprecated `torch_dtype`, the tokenizer's clean-up, "use a dataset", torch's "Redirects are currently not supported") are left out.

### Changed

- The settings window is in the game's own tabs

  «Общее», «Каналы и чтение», «Голоса», «Словарь» instead of one long window and three more behind buttons. Each tab starts with a line on what is on it, and the window is as high as the tab needs. Speed and volume are on the first tab; the bridge settings are its foldable section; the Windows voices list and the dictionary are tabs of their own. The «Общие каналы» box holds its channels under it, as «Озвучивать имена» does. Channel labels carry this client's own chat commands («Группа (/гр)»), and the settings say plainly whether the companion was running at login.

- Everything on «Каналы и чтение» is on by default

  Names, surnames, the verb, officers, emotes, own lines, numbered channels; saved settings stay as they are. In retail the tab has no «и фамилии» (retail names have no spaces) and no waiting for CatQuest and Wayfarer (Forever's addons).

- The speed and volume sliders' 100 % is the default sound

  It used to be 125 % speed and 120 % volume, which sounded better; the speed goes 40–160 % and the volume 0–200 %, so both marks stand in the middle at 100. Saved settings are converted once, so everything sounds as before.

- The program learns where the strip is from the addon

  The addon tells it before moving the strip, on the strip where it still is; no chat line is lost while it moves. If the program misses that, or is started while the game runs, it reads the place from the addon's saved settings, and failing that finds the strip anywhere in the game window within seconds.

- One model cache

  The companion keeps every model in one Hugging Face cache (`hf_home`, by default the `hf` folder next to it): Whisper, used to build the voice bank, lay in the system's cache apart from F5 and Vocos.

- Dictionary

  «тг» as «телеграм», «ага» with the stress on the last «а», «доведёте» (and «доведёт», «доведёшь», «доведём») and «Серёжа» in every case with «ё», «чиловая» as «чил+овая» in every form, «пиши» as «пиш+и», «губа» as «губ+а», «тикет» as «т+икет» in every form, «хелло» as «хелл+оу», «менеджмент» and «манаменеджмент» with the stress on «м+е» in every form, «др» as «дэ-+эр», «нюдес» (and «нюдсы») as «н+юдес», «чето» as «чёто», and «берет», «берете», «ружье» as «берёт», «берёте», «ружьё» (the «ё» dictionary leaves these: «берет» is a beret too, «ружье» a case of «ружьё»). «РЛ» is read as «руины Лордерона» (declined after a preposition: «у руин Лордерона»), and as «рейд-лидер» where the words around it say so («нужен РЛ», «РЛ сказал», «пишите РЛу», «с РЛом»). Declension: a hyphenated word declines as one («с рейд-лидером»), and «руины» as a thing («в руины», not «в руин»).

- «1 место» is a count

  Read as «одно место» (it was «первое»): in chat it is mostly «1 место в группу»; «15 место» and «на 2 месте» stay ordinal.

### Removed

- BREAKING: `/wcv reset`

  Handing the race voices out again is the «Перераздать голоса» button, which asks first; a command for a thing done once in a blue moon is one more to remember.

- BREAKING: «Склонять замены после предлогов» and «Только то, что видно в окнах чата» are no longer settings

  Both are always on.

### Fixed

- `/wcv last` no longer loses lines

  A replay of more than 8 lines went past the companion's queue, and the extra ones were dropped (on a 14-line replay, 6 were); over 20 lines, the strip's queue dropped the first ones too. Replayed lines are now never dropped and do not count toward the queue's 8 live lines, and a line already made into sound waits for its turn instead of being thrown away. It remembers the last 50 lines across `/reload` and a game restart: they are kept in the addon's saved settings.

- The companion stops when the addon is not installed

  At once, saying where it looked and what to do — instead of launching the game and reading nothing.

- The race voices option no longer says they come from CatQuest

  Since 0.2.0 they come from the game's own Russian voice-over.

## [0.2.1] - 2026-11-12

### Added

- One speech per character

  Several lines in a row from one character in one channel are read as one speech: the name only before the first, when the next line comes while the previous one is still being read or within 5 seconds after it ends (someone else in between — the name again).

- Where the strip is can be set

  «Мост…» in the settings (the strip is called the bridge there, with a tooltip on what it is; the program is the companion app there, «приложение-компаньон», or just «компаньон»): the top edge (as before), the bottom edge, or a place of your own (X, Y and width in screen pixels; the fields start from the top or bottom line's numbers). Another addon drawing in the same place — such as wow-ai, which draws its own strip in the top left corner — hid ours, and chat lines were lost while it was up. While the window is open, an orange frame shows where the strip will go; «Сохранить» moves it.

- `/wcv debug`

  The addon notes in the program's log each chat line it does not send, with the reason (chat type off, not shown in any chat window, hidden by another addon's chat filter, your own), and when CatQuest starts and stops speaking — the log has the time the game's chat lacks.

- Dropped lines are noted in the program's log

  A chat line dropped after waiting too long for CatQuest, and one dropped because the queue is full (more than 8 lines waiting in a busy chat); before, they vanished without a trace.

- Ordinals where only an ordinal fits

  «с 15 уровня» — «с пятнадцатого уровня», «на 2 этаже» — «на втором этаже», «15 уровень» — «пятнадцатый уровень». With words that number rather than count (level, floor, place, rank, phase, season, chapter, act, wave, slot, boss) also «с 21 уровня» — «с двадцать первого» and «хил 15 уровня» — «пятнадцатого». Counts stay counts: «200 опыта», «на 2 уровня выше», «5 раз». «Число» as a date is a word that numbers: «до 11 числа» — «до одиннадцатого ч+исла». After an ordinal, «числа» and «места» get the singular's stress: the stress model always took them for the plural («числ+а», «мест+а»).

### Changed

- The dictionary is applied by the program

  It reads the default dictionary straight from the addon's files and picks up a change within seconds, with no `/reload`; your edits from the dictionary window come to it as before. A character's name is no longer run through the dictionary (a character named «Лок» stays «Лок»).

- CatQuest cuts in

  When CatQuest starts speaking while a chat line is being read, the chat stops at once and waits; once CatQuest is silent, the line it cut is read again from its start, then the rest. A pause whose end never reaches the program ends by itself after 90 seconds.

- Dictionary

  «че» as «чё», «серега» as «серёга», «пикабу» as «пикаб+у», PvE as «пэ-вэ-йе»; «аук» in every case as «аукцион» («на ауке» — «на аукционе»), and the Ragefire Chasm typed in full as «Огненная пр+опасть», not with the verb's stress «пропа́сть», in the case its preposition asks for («в Огненная Пропасть» — «в Огненную пропасть»); «танчить» as «т+анчить» in every form, «МСК» as «эм-эс-к+а»; «кв» as «квест», and a number before «шт» as so many pieces in the right form: «6шт» — «шесть штук», «1 шт.» — «одна штука».

### Fixed

- The chat no longer waits for a stuck CatQuest

  When CatQuest reports a track still playing well past the track's own length: its «playing» gets stuck at times, and chat lines were held and then dropped while nothing was heard.

- Item links and a colon before a Russian letter

  Item links coloured by quality name (`|cnIQ1:`, as newer clients send them) no longer leave the colour code in the speech, and two links in a row are read as two names. A colon right before a Russian letter («1:Сильный», «внимание:Привет») no longer garbles the letter: the rule for the «:Р» smiley took the Russian «Р» apart into bytes and ate the first byte of the letter.

- The strip is drawn above the rest of the interface

  It belonged to the game world's frame, and everything in the interface — the minimap at the top right, the action bars at the bottom — was drawn over it whatever its layer. It still stays up when the interface is hidden (Alt+Z).

- The strip is as thick as the longest line needs

  A narrow place of your own gets more rows (220 pixels wide — 7 rows, 14 pixels), and the bridge window shows the thickness. On a 1280-pixel-wide screen it now has two rows: one held 469 bytes, and parts of your dictionary edits (480 bytes) came to the program cut.

- A quest's number after its name is not read out

  The number quest addons put after a quest's name in chat («[[25] Свиток с рунами (3513)]»).

## [0.2.0] - 2026-11-11

### Added

- BREAKING: race voices come from the game client itself

  The Russian voice-over of the playable races: each race and sex has the player character's voice and three NPC voice types (orc guard, shady and standard; human official, standard and warrior; …), each also in a lower and a higher copy, 12 voices per race and sex. Real actors instead of synthesized CatQuest voices: the orc sounds low and rough and the speech comes out clearer. CatQuest is no longer needed. The client's files are only read, never changed, and the game is not touched: the voice bank is made on your machine before the game starts, the first time and after each game update (a few minutes: Whisper hears the lines for their text), and kept until the next update. Races without voices of their own in the client speak as their kin: goblins and vulpera as gnomes, blood elves as night elves, and so on. If you pinned a race voice to a player in `players`, the voice names changed (`orc-male/standard` and the like).

- The chat waits for CatQuest

  While CatQuest reads a quest, chat lines wait and are read once it is done (lines that waited over 40 seconds are skipped); a setting, on by default. The quest is not paused for the chat instead: the game cannot resume a sound in the middle, so the quest would start over after every chat line.

- Hidden swear words are read as the words they are

  A bracket pair for «х» («на)(уя»; it used to become a full stop), Latin look-alike letters («xyйня»), a digit inside a word («п0шел») and asterisks for letters («бл*ть»).

### Changed

- Slow voices speak faster, and each character at a tempo of their own

  The game's recordings differ up to fourfold in tempo (a hurried error message of a character, a solemn NPC greeting), and a voice slower than the faster quarter of the voices is drawn most of the way toward it (by at most 1.8 times; the Tauren elder went from 18.5 to 12.3 seconds on a test line); faster voices stay as they are. Each character also speaks at a tempo of their own (±8 %, from the name), so two characters given the same voice still sound like two people.

- The race voices load while the game starts

  Instead of waiting for its first chat line (unless the addon was last set to Windows voices).

- Quest and item links read as their names

  No brackets, no quest level tag («[24]»), and the word before a link no longer runs into it.

- Words in capitals are read as words

  «РАЗЫСКИВАЕТСЯ», «ВСЁ», «СТОЙ» — not as abbreviations with the stress in the wrong place; an abbreviation the dictionary does not know is read letter by letter when it cannot be said as syllables, as in Russian speech: «ППС» — «пэ-пэ-эс», «ЦРУ», «США», and a syllable it begins with is said as one: «ГИБДД» — «ги-бэ-дэ-дэ»; «ОМОН» or «ВУЗ» are read as words.

- `assignments.json` forgets characters not heard for 60 days

  It no longer grows without end on a busy server: one who comes back gets a voice again, the same one when there are voices to go round, and the file is written every 30 seconds and on exit instead of on every chat line.

- Dictionary

  Discord as «диск+орд», the Crossroads as «перекр+ёсток» and greaves as «п+оножи» in every case, and «ПС» as «Пещеры стенаний».

### Fixed

- Endings no longer get cut off

  When a line's speech runs to the very end of the length given to it (one line in ten), it is made again with a quarter more length.

- Very high and very low voices no longer rasp in questions

  The pitch analysis behind the question intonation had a fixed 60–500 Hz range, and gnome women speak at 450–500 Hz, the orc character at 55–70 Hz; outside the range it lost the voice's periods. It now follows the voice.

- Numbers get their stress like other words

  «шестн+адцать», not «ш+естнадцать»: they are turned into words before the stress marks are put, not after.

- A word the stress model splits keeps the line's other stresses

  A line with a word it splits its own way («RU/UA», «<MIR>») no longer loses the stress marks of all its words («игр+оков» for «игрок+ов»): only that word goes without.

- A dictionary stem keeps the case typed in chat

  An entry with `*`: «на перекрёстке» was turned into «на перекрёсток», as the declension after a preposition is meant for abbreviations («в ОП») that have no ending of their own.

## [0.1.0] - 2026-11-11

### Added

- Initial release

[0.4.0]: https://github.com/rgeraskin/barrens-voice/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/rgeraskin/barrens-voice/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/rgeraskin/barrens-voice/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/rgeraskin/barrens-voice/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/rgeraskin/barrens-voice/releases/tag/v0.1.0
