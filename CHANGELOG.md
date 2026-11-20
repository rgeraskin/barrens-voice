# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> MAJOR is still 0 ([spec item 4](https://semver.org/spec/v2.0.0.html#spec-item-4)): MINOR carries everything that is not purely a fix — new features and BREAKING changes alike — and PATCH is fixes and docs only (0.2.1 predates this rule and added features too). Every breaking change is titled `BREAKING:` — a name, a command, a file or a setting that no longer works as it did — so `grep BREAKING` over this file lists them all.
>
> Release dates are the GitHub release's publication date (UTC). Versions before 0.4.0 had no GitHub release: their date is the release commit's, and their tags were set later on those commits.

## [0.4.0] - Unreleased

### Added

- An installer

  `BarrensVoice-Setup.exe` from the latest GitHub release installs for the current Windows user, without administrator rights, into one folder (by default `%LOCALAPPDATA%\BarrensVoice`): the program, `data` (settings, the voice bank, logs) and `cache` (models). While installing it downloads Python and the libraries through uv — the CUDA build with an NVIDIA card, DirectML otherwise — and the models (~3 GB): about 6 GB on disk with NVIDIA, 4 GB otherwise. The folder has «Barrens Voice.exe» with the app's icon, which starts the current version; the shortcuts and the start at Windows sign-in go through it. Neither the installer nor uninstalling runs over a running Barrens Voice: both ask to close it first. Uninstalling then stops only what is left of this install without its lock (a stray process of its folder) and asks whether to delete the settings, the voice bank and the models too. `BarrensVoice.cmd` stays for running from the source, and downloads the models too (`python -m bv --fetch-models`).

- Updates by themselves

  An installed Barrens Voice checks GitHub Releases at start and hourly and trusts a release only with its signed manifest (ed25519) and an archive that matches it. With «Обновлять автоматически» (on by default) the launcher downloads the new version and builds it beside the current one in the background, with the uv the release names, and switches to it when the game and the voice-over are not running — or at once on «Установить сейчас»: the voice-over stops for about half a minute while the launcher restarts into the new version and starts it again for the running game. With the check off, the notice offers «Обновить». A failed download or build is tried again at the next check. A built version must start in its own Python before it is used (its own `bv/selfcheck.py` says what that takes): one that does not is refused and waits for «Обновить» or a newer version, while a check that could not run at all (a timeout, an antivirus scan) is tried again at the next check. `app\current` is switched through a new link, with the watch over the new version written before the switch, so a failure leaves the old version in place, and a switch cut short still starts (from the new link, else the old one). A version whose companion fails right at start twice is rolled back and remembered: the notice stays, but it is installed again only by «Обновить», until a newer one comes. Only that very version is held back, not an older one of the other channel. An end that says nothing of the version (a restart to go online, another companion running, an unreadable config.json, an error the companion explained, such as no addon) is neither a failed start nor a good one: the next start decides. The current and one previous version are kept; older ones (in the background, without freezing the window, also a few seconds after the launcher starts, so closing with the game no longer cuts it short) and downloaded archives are removed. A version newer than the current one — prepared, or refused — is never removed, and a switch cut short is repaired at the next start. A new version is accepted once its companion has run a minute, even when the launcher always stops it; only folders named like a version are removed from `app`. After an update the launcher starts itself again without starting the game; when it was closing with the game, it just closes. The stable channel never takes a test build. Windows «Apps» shows the version in use. The notice says «Вышла версия 0.4.1 и аддон 0.3.2» (the addon only when it changed), under it what the update does («обновление скачивается… / готовится… / ждёт закрытия игры»), and «Что нового» opens the release's page. The addon follows the app: with automatic updates an older addon is replaced in each game that is not running (a newer one, from CurseForge, stays); otherwise a game's card offers «обновить аддон». «Получать тестовые версии» takes pre-releases: a test build carries its own version (tag `v0.4.0-beta.5` → `0.4.0b5`, shown as «0.4.0 beta 5»), a newer beta is an update, and the release is newer than its betas. Installs of 0.4.0 beta 1–4 compare versions by their numbers only, take 0.4.0 for older than their beta and skip it: they update by themselves from 0.4.1 or a later beta, or by installing again. The app's version is `pyproject.toml`'s now, the addon's its own.

- A launcher window instead of the companion's console

  `BarrensVoice.pyw` opens a window: the state (companion, game, race voices with the video card, the link with the addon), the companion's log, the start options with hints (launch the game with the launcher — off by default, only when it is opened by hand: a shortcut, also while it waits in the tray, never at Windows sign-in; close the launcher with the game — grey while it starts at Windows sign-in, then it always waits for the next game in the tray; start at Windows sign-in, then waiting in the tray), the installed games with the addon's version in each and «установить аддон» / «обновить аддон», «Играть», settings, help and the update notice. Opened by hand it starts the companion only with the game — when the game runs or appears, on «Играть», or with «Запускать игру» on — so the race voices take video memory only for a game. The cross closes it with the companion (asking if the game runs); it hides in the tray by itself when it starts the game and at Windows sign-in; when the launcher ends, the companion ends too. The games are found where they last ran, from the registry and Battle.net's settings, and in the usual folders on every local disk; the settings have a folder field for each game, «Папка WoW Forever» and «Папка WoW Retail» (`game_dirs` in config.json; the single `wow_dir` is still read), ask whether to save changes when closed, and link to the description of config.json. A config.json that does not parse, or cannot be opened at the moment (in use, an antivirus scan), is never written over: the launcher and the companion say what is wrong, and a change made in the settings stays in the window. One that cannot be written (read-only) is said once, and no config.tmp is left; the change holds in the window, goes into the next write, and the companion is started with the window's game and launch choice (config.json is read again before each start, so a hand edit made while the window was open counts); The companion itself no longer refuses to start when it cannot write new settings into a read-only config.json. The log says at once when the chosen game has no addon. Details such as the command sent to Battle.net go to the log window only, also when «Играть» launches the game from the launcher itself. Installing the addon mirrors it into the game: files the new version no longer has are removed, the three the companion writes there (`VoiceList.lua`, `CompanionStatus.lua`, `DictionaryOnline.lua`) are kept; with the game running a `/reload` is enough (checked on Forever's client, new files and pictures included). The window follows the Windows screen scale; its icon is the addon's. `BarrensVoice.pyw` and `BarrensVoice.cmd` take the same switches (`--retail`, `--console`, `--f5`…, `--help`). The main window's log scrolls back over its last 200 lines: the mouse wheel, or a thin bar that shows on the right while the pointer is over the log (dragged, or pressed beside its thumb for a page); the text stops short of the bar, and new lines do not move a view scrolled up.

- The dictionary online

  The default dictionary comes from GitHub without an addon update: CI publishes it, signed, after the tests pass on master (the branch `dictionary`), and the companion fetches it at start and hourly. It takes it only with a valid signature, a format it reads (raised when the dictionary's syntax changes: an older companion keeps its last one), and regexes that compile, run fast and have valid replacements (checked in a process of their own, and in CI before publishing), keeps the last good one for starts without the network, and uses it while it is newer than the addon's own (`revision`, the time of the last commit that changed Dictionary.lua). The companion applies it at once and writes it into the addon as DictionaryOnline.lua, so the dictionary window shows it after `/reload`. `dictionary_online` in config.json turns it off (and empties DictionaryOnline.lua); run from the source it is off.

- Log levels

  Every line of the companion's log carries one — DEBUG, CHAT, INFO, WARN, ERROR — decided by the message in one table (`bv/logs.py`). The launcher's main window shows only how things go (INFO and up, without the level), in plain words and lines written to fit (one that does not wraps under its time; the details are in the full log, indented), and a long job as one line that moves on. «Журнал» opens the full log live, with filters by level, search, «Копировать» (the selection, or every line the filters show), «Копировать для отчёта» (the version, Windows, the ONNX Runtime build, the video cards, the race voices' state, the games with their addon and the settings changed from the defaults — folders, the WoW account and players' names left out, the home folder as `~` — then the last 300 lines of every level) and scrolling that follows new lines only while at the bottom. What libraries write below Python (onnxruntime, progress bars) comes as `DEBUG [stderr]` lines of its own.

- The voice bank's progress in the log

  Building the bank (once, and after each game update) logs «собираю голоса рас: N из M» every 10 seconds, then «голоса рас собраны: N из M за X мин»; the launcher's main window keeps them in one line that moves on.

- Whisper can check a line's ending

  A line whose speech runs to the very end of its length (about one in eight) is made again with more length, as before; the launcher's settings can instead have Whisper listen to its ending first and make it again only when the last word is not heard (`f5_end_check`: `"silence"` by default, `"whisper"` saves a second on such lines for about 1.5 GB of video memory).

- A strip of another protocol is told apart

  A strip whose protocol the companion does not read is not taken for a covered one («полоска видна, но не читается»): after 3 seconds the companion says which to update — «аддон новее Barrens Voice — обнови Barrens Voice» or «аддон старше… — «обновить аддон», потом /reload» — and the launcher's «Мост» line says so. A new protocol keeps reading the one before (`protocol.SUPPORTED`).

- The hidden chat says it needs a `/reload`

  A companion started after the player entered the world says that the hidden chat needs a `/reload`, in the log and as a tray notice. It asks before its first beat (`bv/reloadhint.py`): «Прятать окно чата» on and the addon not switched off in its saved settings, no companion running a moment ago (a restart by the launcher — the addon saw that one), and the strip already on screen. The settings («Общее») say it as well: «при входе в игру компаньон не был запущен — прозрачный чат включится после /reload», the status being for information only (the chat is read either way). At login without the companion the addon says it too, as a line of its own under «…не запущено…»: «прозрачный чат пока выключен: включится только после /reload, когда компаньон заработает.»

- A «Помощь» tab in the settings

  Where to write about bugs, ideas and words read wrong — Barrens Voice's community in Battle.net (the game's «Сообщества»: news and questions), Discord, Telegram and the GitHub issues, each with its icon, its address in a box (a click selects it, Ctrl+C copies), «Копировать» and «Открыть». The game gives an addon neither the browser nor the clipboard, so the companion does both (bridge kinds `open` and `copy`, only for the addresses it knows). The community needs no browser: its «Открыть» closes the settings and puts a line in the chat, with the addon's icon: the community's link «[Вступить в «Barrens Voice»]» in Battle.net's colour and its web address in grey, then what to do — one click on the link opens the game's communities window with «Вступить», with or without the companion and with the voice-over off too; the browser only where the game has no communities. A player already in the community is told so instead, with the key their game opens the communities window with (whatever it is bound to; none named when none is); one who joins within five minutes of «Открыть» is greeted. Its icon is the Blizzard logo the chat shows. Under the links, centred, «Что нового» opens the window of what is new. The welcome on the first run and the «Что нового» window point to it.

- «Что нового» after an update

  What an update brought, in the players' own words (Russian, short), instead of the one line after an update: a few seconds after login (after «озвучка чата работает»), and never in combat (5 s after it ends), a release with something new or changed opens the «Что нового» window — every release's entry, newest first, with its date and a few points, and under them a link row to the full changelog on GitHub («Копировать», «Открыть»); a release of fixes and dictionary words only is just the chat line, which comes with the window too (to open it again): one line with the addon's icon, «Barrens Voice:», a short summary and a [Что нового] link that opens the same window (a click with Shift opens it too and puts nothing into the edit box). Each entry is shown once; a test build shows its release's entry and, above it, its own: «Тестовая сборка N», the list of its commits since the last test build or release that went out (commits that touch the docs only left out), made by the build (never kept in news.toml), and the entries of the release's earlier test builds that went out, newest first, so a tester who skipped one sees what it brought too (the GitHub release lists the build's own only); the first run shows the welcome instead. `/bv news` and «Что нового» on «Помощь» open the window any time, and Escape closes it. «Окно «Что нового» после обновлений» on «Общее» (on by default) leaves only the chat line. The news are the program's: every release has its entry, one with changes to the program alone too, and the companion brings them into the game at its start (`NewsData.lua` in the addon's folder, kept by addon installs), so they show at the next login or `/reload`; until the companion has run, the window says where they come from. The GitHub release's description is the same entry, with a link to this changelog.

- «Отладка» in the addon's settings

  Under «Дополнительно», with a tooltip on what it writes and why to keep it off otherwise.

- The hidden chat shows on a group line

  «Показывать при строке группы/рейда» under «Прятать окно чата», on by default: a party, raid, raid warning or dungeon or battleground group line shows the faded chat window though it is read aloud, as a whisper or a guild line can.

- Where a line was said

  «и где: «Громмаш пишет в гильдии: …»» under the names, on by default: the verb gets the place — «в группе», «в рейде», «объявляет рейду», «в гильдии», «в офицерском чате», and a numbered channel as where the line goes after «пишет» — «пишет в общий», «в торговлю», «в канал <имя>» (not «пишет в общем», which sounded like the writer's own «в общем»), as where it is after «спрашивает» — «спрашивает в общем», «в торговле». With «Озвучивать имена» but no verb a channel goes by its name: «Тралл, общий: …», «Тралл, канал <имя>: …». Only when the place changes from the last line read or after 30 s of quiet, so a run of guild lines names the guild once; say, yell, whisper and emote have no place. Without the verb: «Громмаш, в гильдии: …».

- «Что читать»: only the selected chat tab

  A choice under the channels: «Все включённые каналы, даже не показанные в чате» (every channel on, also one taken out of every chat tab or hidden by a spam filter), «Что показывают окна чата» (as before, the default: any chat window or tab, the tabs not selected too) or the new «Только выбранная вкладка» — of the chat window's tabs only the one on screen, separate chat windows still. For instance: move the group's chat to a tab of its own, select it, and only the group is read. Whisper tabs count as tabs too: with the game's «Шёпот» set to a new tab, a conversation is read while its tab is selected (or pulled out as a separate window), and the general tab no longer reads a whisper it does not show.

- Battle.net whispers are read

  A Battle.net friend's whisper is read under «Шёпот», as a whisper: «Громмаш шепчет: …». A friend in WoW is named by their character, without the realm, and speaks in their race's voice; a friend in the Battle.net app (or not on a character) by their BattleTag without «#1234», in the race voices' default, a human man's; the companion's log shows them «BN:Вася» too, without the digits (the race voice stays tied to the whole BattleTag), and `players` in config.json pins one by that «BN:Вася» or by the whole BattleTag. The history `/bv last` keeps in the saved variables has the BattleTag without the digits as well; a line replayed from it keeps the friend's voice, and when it comes before the friend's first live line (after `/bv reset-voices`, say) the voice it got stays theirs. A whisper from a friend the game does not tell the addon about is not read, and shows the hidden chat. The account's real name is never said or written to the log. One's own Battle.net whispers are read like one's own whispers to characters (below). «при шёпоте» under «Прятать окно чата» shows the window for them too, and «Что читать» counts the chat windows that show Battle.net whispers. On retail they are closed to addons in dungeons, raids, boss fights, Mythic+ and PvP, like the rest of the chat.

- One's own whispers are read with «Свои сообщения»

  The whispers one sends, to a character or to a Battle.net friend, are read under «Шёпот» when «Свои сообщения» is on (as it is by default): «Джайна шепчет: …», by one's own name, in one's own voice, without the name of the one whispered to. The name is the one the chat gives the character's own lines (on Forever the game's own name parts may differ from it), so one's own whispers are read once the character has written a line the addon heard, in any chat; it is kept per character over `/reload` and restarts. Until then `/bv debug` says why one is not read. With «Свои сообщения» off they are not read and the hidden chat shows them as before; read, they show it only with «при шёпоте», like a whisper one gets.

- A dictionary replacement can stay as written

  A replacement starting with «!» («скачки=!ск+ачки», in a regex too) is not put into the case of the preposition before it: «после скачки клиента» stays «скачки», not «скачек». The others are declined as before («в ОП» → «в Огненную пропасть»). The dictionary online is format 2 now: a program before it would read «!» as is, so it keeps its last dictionary until it updates. In the addon's own Dictionary.lua such entries are in a second part of the default, which an older program does not read (a rolled-back program with a newer addon reads these words as before, not «после! скачек»).

### Changed

- The chat waits for NPC lines CatQuest and Wayfarer voice, too

  The server sends only the text of what NPCs say and cry in the world (a city's herald, a mob in a fight); CatQuest's «Голоса мира» and Wayfarer's barks voice them, each in a queue of its own, and a chat line was read over them. Now such a line pauses the chat as a quest does: the line being read is said again from its start, the next ones wait. CatQuest's line is seen in its world queue (`CatQuestCore.WorldQueue.Current`), Wayfarer's through a hook on its `Barks:Play` (the sound's length) checked against `Barks.recent` (it did play). The setting is now «Ждать озвучку CatQuest/Wayfarer» (`waitForCatQuest`, as before). With it off, the debug log no longer says «чат ждёт» of a quest voice-over or an NPC's line: «чат не ждёт: «Ждать озвучку CatQuest/Wayfarer» снята».

- The dictionary window keeps a line where it was typed

  It sorted the text as soon as the box lost focus, and a line just typed jumped to its place in the alphabet. The entries are sorted when the window is shown again; while it is open they stay as typed. Every edit is still saved at once.

- The mod speaks to the player with «ты»

  The addon, the launcher, the companion's log, the installer's starter, README and the player's docs say «ты» instead of «вы»: a fan mod for players, like most Russian addons. The test lines spoken to a group keep their plural, and Windows' own wording stays as it is.

- A raid warning is «объявляет»

  With the verb on, a raid warning is read «Тралл объявляет: …» (it was «пишет»), and never «спрашивает».

- BREAKING: the voice-over always ends with the game, and `exit_with_wow` is the launcher's

  In 0.3.0 `exit_with_wow` false kept the companion running after the game, the race voices in video memory until the next one. Now the voice-over always ends some 10 s after the game it saw and frees the memory, and `exit_with_wow` («Закрываться вместе с игрой») says whether the launcher closes too: on, it closes, off, it waits for the next game in the window or the tray. The key keeps its name and default (true). With the start at Windows sign-in on, the check is grey and unchecked and the launcher always stays; turning the start on takes the check off, so turning it off again does not make the launcher close with the game unasked. `tmp/live.json` is no longer written.

- BREAKING: the mod is called Barrens Voice

  After the Barrens chat. The addon's folder is `BarrensVoice`, its command `/bv`, its saved settings `BarrensVoiceDB`; the companion starts with `BarrensVoice.cmd`, its Python package is `bv`, its logs `bv-YYYY-MM-DD.log`. Nothing carries over from the old names by itself.

- BREAKING: the race voices run through ONNX Runtime instead of torch

  F5 exported to ONNX (DakeQQ/F5-TTS-ONNX, 10 steps; the models from Hugging Face `rgeraskin/barrens-voice-f5-onnx` into the model cache, or your own in `f5_onnx_dir`) and Whisper large-v3-turbo in ONNX for building the voice bank. On NVIDIA they run with CUDA (`onnxruntime-gpu`), and the game does not stutter while chat is read; on any other DirectX 12 card with DirectML, which holds the video card for each whole denoising step (~100 ms), so the game stutters while a line is made. The companion takes CUDA, then DirectML, and refuses a session ONNX Runtime quietly put on the processor instead (DirectML without DirectX 12; another provider set in `f5_onnx_provider`, TensorRT say, is asked for and refused the same way): the race voices fall back to Windows voices at once, without building the voice bank for nothing. Every ONNX session gets two threads that sleep when idle, and the companion runs below normal priority (`share_with_game`, `onnx_threads`). The Python environment is 2.8 GB with CUDA or 0.6 GB with DirectML instead of 6.4 GB; a line takes about 1.1 s on an RTX 5070 Ti, as with torch. The models are downloaded while installing, not at the first start; what fails to download, the first start downloads. `requirements-f5.txt` and the `nfe_step` setting are gone, the library versions are pinned. RUAccent keeps its dictionary and models (`koziev` among them) in the model cache (`hf_home`, folder `ruaccent`), so a new Python environment needs no download. The voice-type tooltip in the addon says «DirectX 12» instead of «NVIDIA».

- The strip is at the bottom edge by default

  «Внизу» in «Мост к лаунчеру…» (it was the top). An addon with saved settings keeps its place.

- The transparent chat fades only with the companion running

  Only while the companion was running at login or the last `/reload`: hidden lines nobody reads would be lost. A companion started later makes it transparent at the next `/reload`.

- «Перераздать голоса» is a command now

  `/bv reset-voices` (it asks first, as the button did): handing the race voices out afresh is rarely needed, and «Общее» has the main switch and «Проверка» across its width.

- The links to more Windows voices are rows

  RHVoice and Silero on «Голоса» are rows of the same kind as on «Помощь»: the address to see and copy, «Копировать» and «Открыть».

- Dictionary

  «95%» is read «95 процентов» (1 процент, 2 процента), «кача» as «к+ача», «рога» (a rogue) as «р+ога» (and «рогов» as «р+огов»), «рмт» / «RMT» letter by letter as «Эр Эм Тэ», «в душе» as the soul «в душ+е» («в душе не знаю»), «см» after a number as centimetres («5 см» — «пять сантиметров», «20см»; a bare «см» is left alone; the dungeon «СМ», Монастырь Алого ордена, in capitals only) in every form, «ЛИ» (in capitals only: «ли» is a particle) as «Лабиринты Иглошкурых», «пздц» as «пиздец», «импрувед» as «импр+увед», «лк» as «эл к+а», «бк» as «бэ к+а», «дс» as «диск+орд» (it was «дисконнект»: in chat it is mostly Discord), «спек» as «сп+ек» (the «ё» dictionary made it the verb «спёк»), «<3» at the end of a line (and «<333», «</3») as a smiley — a pause, it was «три»; inside a line it stays a number («кд <3 сек», «<3к»), «долбаеб…», «долбоеб…» with «ё» in every form, «бтв» as «кстати» (as «btw»), «скрафтить» as «скр+афтить» and «вендор» as «в+ендор» in every form, «нп» in lower case as «без проблем» (the dungeon «НП» in capitals only), «скачки» as downloads «ск+ачки», as spikes («скачки фпс», «скачки пинга») «скачк+и», «ниче» as «ничё», «темп» with a hard «т» in every case («тэмп», «тэмпом»), «лвл» in every case («лвла» — «уровня», «с лвлом» — «с уровнем»), «х3» and «х2» as «икс три», «икс два», «+-» as «плюс-минус» (also before a number: «+-5 минут» — «плюс-минус пять минут»), «2х2», «5x5», «3v3» as «два на два» (and «2х2 арена» — «два на два арена»; «40 х2» — «сорок икс два»; unequal numbers around «на» are a count and a place: «нас 3 на 2 боссе» — «нас три на втором боссе», «с 2 на 3 место» — «со второго на третье место», «пересел с 1 на 2 группу» — «с первой на вторую группу», while «перешли с 10 на 25 человек» stays a count), «2г50» as «два золотых пятьдесят», «2г50с» as «два золотых пятьдесят серебра», «играю с 2005г», «в 2007г» as a year (after с/в/после, and a range of years: «с 2005г по 2010г» — «… по две тысячи десятый год»; «продам за 2000г» stays gold); Discord's emoji codes («:lol:», «:+1:») are dropped before the dictionary.

- Library notices left out of the model download

  The model cache's warning about symlinks on Windows (it keeps plain copies without developer mode, which costs nothing here) and two of RUAccent's own notices (a regex string without `r""`, an argument huggingface_hub ignores) are no longer shown.

- The settings say what retail does not let be read

  On retail, the «Каналы и чтение» tab says on top that the game closes the whole chat to addons in dungeons, raids, boss fights, Mythic+ and PvP: there nothing is read.

- The login line and the first run's welcome are easier to see

  «озвучка чата работает» (or that the launcher is not running, and the line about the transparent chat after it) comes 5 s after login and `/reload`, as the welcome on the first run does right after it, then what is new after an update: other addons' lines at login no longer bury them. The welcome's lines have the addon's icon, as every line of the addon does, and it names the community in Battle.net among the places to write. Its words are friendlier, in the style of the addon's other texts, and name no version (it means nothing to a player): what the settings hold, that the launcher starts the game and the voice-over, an ask to write and «Приятной игры!».

- Whispers and guild lines show the hidden chat by default

  «Показывать при шёпоте» and «Показывать при строке гильдии» under «Прятать окно чата» are on by default now, as «Показывать при строке группы/рейда» is: a whisper is easy to miss by ear.

- The settings' tooltips are in paragraphs

  A long tooltip was one dense block; now what the setting does, the details and the caveat are paragraphs with an empty line between, as the game's own tooltips are, and «с глаголом» lists its verbs a line each. Tooltips and labels name no chat commands: «Отладка», not «Отладка (/bv debug)»; «Помощь» says where they are («Список команд чата — /bv help»), and the game's settings panel keeps «или /bv в чате».

- Every message of the addon in the chat starts with its icon

  A small icon of its own: the speech bubble on a clear background (`Media/chat.tga`), not the framed icon, an opaque dark square on the chat's clear background. Not only the welcome, the community and «Что нового»: the login line, the answers to the commands and buttons and the warnings too, before every «Barrens Voice:», a message's next lines too (the welcome's, the community's second, «прозрачный чат пока выключен…»); only lines without the prefix, the list of commands, go without it.

- The program is called Barrens Voice Launcher

  The addon, the program on Windows and the mod all went by «Barrens Voice», and the program by three more names besides: «программа» in README, «приложение-компаньон» and «компаньон» in the game and the launcher. Now the program is «Barrens Voice Launcher» («лаунчер» for short) in README, the addon's messages and settings, the launcher's window, dialogs, tray and log, and what reads aloud inside it is «озвучка» («озвучка запускается», «озвучка остановилась»). «Barrens Voice» is the mod as a whole. The shortcuts, `Barrens Voice.exe` and the entry in Windows «Apps» keep their name. The default dictionary's header says the launcher applies the regexes («регулярки (Python, применяет лаунчер)»); a header the player changed stays theirs.

- «Играть» is grey while the game starts

  From the launch until the game's process is seen the launcher's big button reads «Игра запускается…» and takes no click: a second click asked Battle.net once more. Every launch counts: «Играть», the shortcut and the window's start with «Запускать игру вместе с лаунчером». The button comes back when the launch gives up (no Battle.net, a game already running, Battle.net did not start it), when the voice-over ends before it launched, or 130 s after Battle.net was asked with no game.

- The launcher's «Помощь» as the addon's

  The window had Discord, Telegram and GitHub under words of its own. Now it has the addon's «Помощь» tab's words, its paragraphs an empty line apart as there, and Barrens Voice's community in Battle.net first: the Battle.net logo (Simple Icons, CC0: the addon's Blizzard logo is the game's own texture), the invite address, «Копировать» and «Открыть» (in the browser). The hint of «Копировать для отчёта» in «Журнал» points to it, the nearer one, instead of the addon's tab.

### Removed

- BREAKING: `WowChatVoice-Retail.cmd`

  The game is chosen in the launcher's window, or with `--retail`.

### Fixed

- Lines under another addon's strip are no longer lost without a word

  With another addon's strip (wow-ai) over a part of ours, every chat line went unread and the log said nothing: the addon holds a line half a second and then its empty frame, which the open part still carries, so no cover lasted the second «полоска видна, но не читается» waits for. The companion now tells the lines it skipped from the frame numbers — «строки с полоски не прочитаны (кадров: N)…», and sends the player to «Мост к лаунчеру…» to move the strip to a free place; under a lasting cover it is said in full once, then at most once a minute with the frames skipped since, and in full again for a cover after ten minutes without one. The lines under the cover are not read: that would take another cell order, a new protocol, and the warning is enough.

- One friend, one voice: a Battle.net whisper and the character's own

  On Forever a friend whispering through Battle.net was «Имя Фамилия-CAMWOWEU5Realm3PvE» (the server's inner name from Battle.net), as the character «Имя Фамилия» (the chat writes no realm: names are unique in the region) - two senders, two voices. With RegionalUniqueNamesEnabled the Battle.net sender is the character's name alone, as Blizzard's friends list shows it; otherwise name and realm as before.

- A RUAccent download cut short is fetched again

  The first start stopped while RUAccent downloaded its dictionaries (the launcher closed, the network gone): every later start ended on «FileNotFoundError: … yo_words.json.gz», since RUAccent fetches a part only when its folder is not there. A load that fails for a missing file (FileNotFoundError, ONNX Runtime's NoSuchFile) now removes the folders RUAccent checks (`dictionary`, `nn/nn_omograph/<size>`, `koziev`) with a WARN line and loads again; its files already downloaded are not fetched again. Offline (the models marked complete, a file gone since) the same: RUAccent then asks the model cache's hub for the folders, and the companion starts again online, as for any model missing from the cache (the hub's «offline mode is enabled» is a DEBUG line, not a red ERROR in the launcher's window). Another error — no network, a file held by another program — is not taken for a cut download.

- A broken config.json is said once, plainly, and the voice-over does not start on it

  The main window had the error twice — the launcher's warning with the JSON parser's English, the voice-over's error — after the voice-over had started only to stop with code 5. Now the launcher does not start the voice-over while config.json does not read, says one error in the player's words («config.json не читается: ошибка в строке 3, столбец 3 — исправь его («Открыть config.json» в «Настройках»)…», the parser's words in the log window), shows «config.json не читается — открой «Настройки»» as the state line and in the tray icon's hint, and says when the file reads again (checked every 2 s). A file that does not open (another program holds it, its permissions) is told so, with what to do about that; one held for a moment is read again after 0.1 s and is no error. «Играть» says the error again.

- Turning «Обновлять автоматически» on prepares a version found already

  A version found while automatic updates were off waited for the next check (at start or an hour later) after the box was ticked and saved. Saving it on, or another channel («Получать тестовые версии»), checks at once now: the version found is prepared, and installed as always once no game and no voice-over run.

- «полоска аддона пропала» names the causes there are

  It guessed «игра свёрнута или скрыт интерфейс», and neither fits: a minimized game has its own line («окно игры не найдено или свёрнуто»), and the strip has not hidden with the interface since 0.2.1. It says now «озвучка выключена в игре (/bv off), экран загрузки или полоску закрыл другой аддон?».

- «Мост: связь с аддоном есть» under a minimized game

  With the game minimized the launcher kept the green «связь с аддоном есть»: the companion dropped the link only on missed frames, and there are none to miss without a window. The link now goes with the window, and the launcher says «Мост: окно игры свёрнуто или не найдено».

- «установится, когда закроешь игру» only while a game or the voice-over runs

  A version prepared with no game running said it would install when the game closed, and switched the same second. The update now says only «версия … готова»; the launcher adds «установится, когда закроешь игру» once, when the switch really waits, and «…когда остановится озвучка» when the voice-over waits on its own: it has seen no game yet.

- «в первый раз скачивается ~760 МБ» only when it does

  The log said F5's models were being downloaded at every online start, though they were in the cache and nothing was fetched. The cache is asked first now, without the network, and the line comes only with a real download.

- The companion in a console with its output in a file

  `python -m bv > out.txt` in a console whose code page has no «×» (cp1251) stopped at the first «экран 1920×1080»: the output goes in UTF-8 now, a character it cannot take replaced. Under the launcher nothing changes (it sets PYTHONUTF8).

- A video card's failure is no reason to fetch the models again

  With the models already downloaded, any failure of the race voices — TensorRT not starting, say — was taken for a model missing from the cache: the companion restarted to go online and forgot that the models were there, so every later start went online too. It restarts now only when a model really is missing; otherwise it reads with the Windows voices, as it says.

- The restart to fetch models works in the console too

  A companion started in the console (`python -m bv`) that found a model missing from the cache restarted itself still offline and failed at once («OfflineModeIsEnabled»): the new process inherited the offline switches. It starts online now, as under the launcher.

- The /reload reminder after a quick restart with a /reload between

  A companion closed and started again within a minute took the addon for having seen the previous one, and gave no reminder, though the game had been reloaded in between without it and kept the chat visible. Now a /reload since (the game writes the addon's saved variables then) counts: the reminder comes. A restart by the launcher, with no /reload between, still gives none.

- A «|» typed in the dictionary window is a «|»

  The game's edit box keeps a typed or pasted «|» as «||», and the window saved it so: a regex «~\b(тестраз|тестдва)\b=окей» became «(тестраз||тестдва)», whose empty alternative matches everywhere («тестдва привет» was read «окейокейокей окейприветокей»), and the message about a too long line showed «||». The window now shows the text escaped and takes it back unescaped, and edits saved so by the test builds are taken back to «|» once at login.

- The strip is found at once after a restart mid-game

  The addon's saved variables keep the strip's place only from the last /reload or logout, so a companion restarted during the game (saving the launcher's settings, «Установить сейчас», a crash) after the strip moved looked in the old place and searched the window for some 8 s. The companion keeps the last place it knew itself now, per game, and starts with whichever is newer; the log says which.

- Starting the game when Battle.net is not running

  Battle.net drops the launch command while it starts and logs in, so the game did not start. The command is sent once more when its window is up (or after a minute) — only once: a second one may start a second game.

- Numbers in chat are read as meant

  A number before «+» (the addon says it as «плюс») was taken for an ordinal of the noun «плюс»: «От 50+ лвл» was «от пятидесятый плюс уровень», «18+» — «восемнадцатый плюс». Now «от пятидесяти плюс», «восемнадцать плюс», «на три плюс человек». An ordinal's ending typed with the number is read with it: «с 2007го» — «с две тысячи седьмого», «после 40го» — «сорокового», «на 4м этаже» — «на четвёртом», «идём в 4м» — «вчетвером», «из 2х» — «из двух». Letters glued to a number are read apart: «200ХП» — «двести ХП». The ending agrees with the noun after it: «на 10й минуте» — «на десятой»; a case ending of a count is the count's form: «до 5ти человек» — «до пяти»; «в 40ку» — «в сороковку»; a lone «м» without a noun after it is a letter («до 5м» — «до пяти м»). «+-» is «плюс-минус».

- Slang taken for a place name is not declined

  «для кача» was read «для качи»: the declension knows «Кача» as a town and declined the dictionary's «к+ача» as its name. A word it knows only as a name, written in small letters, stays as typed.

- Discord's emoji codes are not read out

  «:handshake:» and the like are left out of the speech.

- A space between the speaker's name and the line

  «Вася пишет:привет» in the log and to the synthesis, and an emote said «Васясмеётся»: `text.plain` stripped the line's leading space. `protocol.with_name` joins them with one.

- «Компаньон не запущен» after the companion stops

  A companion that stops (closed, crashed, ended by the launcher) marks its status file so: an addon loading after that says the companion is not running instead of «озвучка чата работает» from a beat of its last seconds.

- «полоска видна, но не читается» is cleared

  When the strip reads again («полоска снова читается») or goes away: a second cover in the same session was not logged.

- Lines another addon's chat filter hides are not read on Forever

  The check called a function Forever does not have, so a spam blocker's hidden lines were still read aloud. Filters are now asked through the client's own `ChatFrameUtil`, and one that fails counts as not hiding.

- «спрашивает» for questions with «р», «Ц», «—» or «№»

  The «…» in the question check was taken as three loose bytes, and «кто в рейд?» or «Цена?» counted as not a question.

- Nothing stale after `/bv on`

  With the reading off, the strip still queued its frames, and `/bv on` played old test lines and opened links clicked long before. Nothing is queued while it is off, and turning it on sends the settings and the dictionary afresh. `/bv off` also drops the chat lines held for a quest voice-over (CatQuest, Wayfarer), which were read after `/bv on` once the quest ended. While it is off, what would ask the companion — `/bv test`, `/bv last`, `/bv stop`, «Открыть» and «Копировать» of a link, a Windows voice sample, «Озвучить» in the dictionary window — says the voice-over is off instead of its usual word (a link still shows its address), and the voices switch says the companion takes it at `/bv on`. `/bv reset-voices` asked for while off waits for `/bv on`, over a `/reload` too.

- «Озвучить» right after a dictionary edit uses the edit

- A dictionary line over 480 bytes is said, not sent cut

  It is left out of what the companion gets, over the strip and from the saved settings alike, so a rule never works in one session and not the next; cut, a regex would be another rule or a broken one. The chat says so once, when the line appears (not at every pause while it is typed), with its `|` shown as typed.

- The strip draws a frame from one edge while it moves

- Units after a number are not taken for a preposition

  «5с кд» was read «пятьс кулд+ауном» and «10к хп» «десять тысяч здоровью»: the «с» or «к» of the number was taken for a preposition and declined the next word. «из-за» and «из-под» now decline too.

- Numbers before «хп», a hyphenated word or after a colon

  «осталось 100 хп» is «сто здоровья», not «сотое здоровье», «нужно 5 рейд-лидеров» keeps its count, and «20:00 сбор» no longer reads «двадцать:нулевой»: it is «двадцать:ноль ноль», «20:05» «двадцать:ноль пять», and «20-00» with a dash is a time too («в 21-00 рейд» was «двадцать один-нулевой»).

- Thousands, gold and seconds after a number

  «к» with a space was always thousands: «+5 к силе» was «плюс пять тысяч силе», «обмен 2 к 1» «две тысячи один». Now «к» after a space is thousands only before an amount (голды, хп, урона…) or at the line's end: «плюс пять к силе», «два к одному», «10к хп» — «десять тысяч здоровья». After «плюс» (the addon's «+») «к» is always the preposition: «+5 к урону» — «плюс пять к урону», «+100 к здоровью»; a dative after «к» is the preposition too. «N к» is thousands before what players count in thousands (дпс, хпс, гс, чести, репы, рейта, хила) and before до/или/и/a dash: «от 5 к до 10 к» — «от пяти тысяч до десяти тысяч»; after a price and before a trade word too: «за 5 к отдам» — «за пять тысяч отдам», «нужно 5 к срочно» — «нужно пять тысяч срочно» (but a dative after the price is the preposition: «до 5 к вечеру буду»); «500 к репутации» stays a bonus. A round price glued to «г» after «в» is gold, not a year: «обошлось в 2000г» — «в две тысячи золотых» («в 2007г» is still «в две тысячи седьмом году»). «100г» was «стог»: «г» glued to a number is gold, «сто золотых». «за 2 кк» was «за два окей»: the word «кк» went before the rule for millions, now it is «за два миллиона» (and «кк» alone is still «окей»). «5 с кд» is «пять секунд кулд+аун», not «с кулд+ауном». «с» after a number was silver before any word: «нас 5 с хилом» was «нас пять серебра хилом», «2 с половиной часа» «два серебра половиной часа»; spaced it is silver only at a phrase's end or as a price goes on («продам за 5 с», «5 с за штуку», «5 с 20 м»), seconds after a cooldown («кд 30 с» — «кулд+аун тридцать секунд»), and a number agrees past «с половиной»: «два с половиной часа», «две с половиной минуты».

- Numbers after «у», «до», «без» and other prepositions of the genitive

  A count stayed in the nominative: «у 5 игроков» was «у пять игроков», «без 2 танков» «без два танков», «до 5 утра» «до пять утра». Now «у пяти игроков», «без двух танков», «из-за двадцати двух боссов», «до пяти утра», «до двух дня», «с восьми вечера», «с пяти до десяти», «нет пяти игроков». A range numbers what follows it: «с 1 по 5 уровень» — «с первого по пятый уровень» (it was «с один по пятому уровню»), «с 1 по 3 босса» — «с первого по третьего босса». A date numbers its day: «до 5 мая» — «до пятого мая», «с 1 по 5 января» — «с первого по пятое января». «инвайт с 60 лвл» is «с шестидесятого уровня» (it was «с шестидесятым уровнем»), «от 55 лвл» «от пятьдесят пятого уровня». Two numbers joined by «-» or «/» share the case: «до двух-трёх человек», «осталось одно-два места», «до одного-двух мест», «пятого-шестого мая». A large number is an amount before a genitive («до 225 навыка») and over a thousand, elsewhere an ordinal: «занял сотое место», «тысячный игрок»; «в 2026 году» — «в две тысячи двадцать шестом году», «в 21 году» — «в двадцать первом году»; «на 1-2 ночи» — «на одну-две ночи», «с 1-2 до 5» — «с одного-двух до пяти». «до 2к» is «до двух тысяч». A singular noun in the case the preposition asks is an ordinal: «до 15 места» — «до пятнадцатого места», «с 2 места» — «со второго места» (с, в, к and о take their long form before the number's word: «во второй сумке», «об одиннадцати боссах»). An amount stays an amount: «до 200 опыта» — «до двухсот опыта», «без 50 маны», «от 300 защиты». The dictionary's number forms follow: «для 2 танк» — «для двух т+анков», «до 2%» — «до двух процентов». «рл» after a number is the raid leader: «нужен 1 рл» — «один рейд-лидер», «нужно 2 рл» — «два рейд-лидера» (it was «руины Лордерона»).

- Spelt abbreviations keep their stress on a vowel

  «МВД» was «эм-вэ-+дэ», and Windows voices that do not take stress marks read the «+» aloud. Now «эм-вэ-д+э».

- The dictionary's regexes match the same with declension off

- «Лок'тар огар!» is not «чернокнижник'тар»

  A word joined to the next by an apostrophe is not a dictionary entry.

- «*да*» and «@Вася» are not unmasked into swear words

  Asterisks around a whole word are emphasis and «@» before a name a mention: both are dropped.

- A Windows voice sample no longer unloads the race voices

- Race voices: an empty voice bank is an error, and a failed load is not retried on every line

  A client without Russian voice-over on disk made the race voices «ready» and silent. Now they say why and the chat is read with Windows voices; a failed load is tried again after 10 minutes or after switching voices off and on. A bank without race voices is refused before the models are loaded, so that retry loads nothing for nothing.

- A very short question is read, with its intonation as it is

  A question of a fraction of a second was too short for the pitch analysis, and its line failed.

- A line that fails to play no longer silences the companion

- A damaged voice bank is made again

- Programs named like the game are not taken for it

  Any `wow*.exe` counted as the game (WowUp, say): the game was not started, and the companion did not close after it. It is now `Wow.exe` in a game's folder. Only before starting the game does one named like it whose path cannot be read (the game run as administrator or by another Windows user) still count: better a launch left to the player than a second game.

- No second game when the player starts it while the voice bank is built

  When the game is launched with Barrens Voice and the voice bank is out of date (a game update), the bank is built first and the game asked for after it; a player who started the game meanwhile got a second one. The launch now does nothing while a game runs, and the log says why («игру не запускаю: она уже запущена…»; a Wow.exe run as administrator counts, another program named like the game does not), and the log says up front «игра запустится, когда соберутся голоса рас» when the bank is about to be built.

- An unreadable config.json is said in words

  The companion stopped with a traceback; it now says where the error is and leaves the file alone. A value it cannot use is replaced, with a warning: a number too small (`"max_queue": 0`, `"voice_pace_limit": 0`, which divided by zero) by the least allowed, one that is no finite number (`"inf"`, `NaN`, `null`) or `null` where a list or settings belong by the default. A gain typed wrong in `kind_gain_db` costs one line, not the race voices. A file saved by Notepad as «UTF-8 with BOM» is read, as the launcher already read it.

- A locked VoiceList.lua no longer stops the companion

  The files the companion writes into the addon are written through a temporary file (DictionaryOnline.lua emptied too), and a swap that fails leaves no `.tmp` behind.

- Lines play again after the temporary folder is cleaned

  The folder for the lines' sound files was made only at start: removed while the companion ran (a temp cleaner), no line could be played any more. It is made again when missing.

- config.json's `_help` is this version's

  The file kept the help text of the version that made it; the companion now puts its own there at every start.

- A screen grab that keeps failing no longer spins the companion, and a voice bank file cut short counts as missing

- A character from another realm is named without the realm

  The name before a line was said as the chat shows it, with the realm of a character from another realm («Вася-Степи»). It is said without it now; the companion still tells characters apart by the whole name, so each keeps their voice.

- The hidden chat goes by the line each window shows

  A channel line read aloud marked every chat window as read, also one that does not show that channel: an addon's message or a system line there within half a second did not show the window. On retail, `/bv debug` called a line of the closed chat «строка не из события чата». The addon now judges the line the window actually adds, by the event the window passes with it: nothing is left marked, and a closed line is «закрытый чат».

- The hidden chat's edit box comes back as the game shows it

  In the «im» chat style the edit box stays under the chat between messages, dimmed by the game. With «Прятать окно чата» it came back fully bright when the window showed or the setting was turned off; now it comes back as the game last set it — dimmed between messages, bright while the player types or with the newcomer's hint.

- The hidden chat leaves frames with a secret name alone

  On retail a frame's name or parent can be secret. Under the mouse, such a frame could raise a Lua error while the hidden chat looked for the chat window under it; it now counts as not the chat.

- Retail leaves CatQuest and Wayfarer out

  They are Forever's addons. On retail `/bv debug` no longer promises their speech in the log, and the addon no longer checks four times a second whether they speak.

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
