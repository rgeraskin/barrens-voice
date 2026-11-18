-- The addon's text functions (Text.lua) on their own: no WoW API stubs at all. Any global the file
-- reads that plain Lua has not is an error here, and so is a global it leaves behind - Text.lua
-- must stay pure, so that this test can load it.
-- Run: mise run test-lua (from addon/BarrensVoice, it loadfiles the addon by relative path)
local before = {}
for k in pairs(_G) do before[k] = true end
setmetatable(_G, { __index = function(_, k) error("Text.lua reads a global plain Lua lacks: " .. tostring(k), 2) end })

local ns = {}
assert(loadfile("Text.lua"))("BarrensVoice", ns)
for k in pairs(_G) do assert(before[k], "Text.lua left a global: " .. tostring(k)) end

local function eq(got, want, what)
    if got ~= want then error(("%s: got %q, want %q"):format(what or "", tostring(got), tostring(want)), 2) end
end

eq(ns.SEP, "\31", "the payload separator")
-- a service frame: kind, five empty fields of the sender, options, text (Core.lua and the companion's protocol.parse)
eq(ns.ServiceFrame("stop", "rate=125", "-"), "stop\31\31\31\31\31\31rate=125\31-", "a command")
eq(ns.ServiceFrame("test", "voice=sapi", "Привет", "Проверка"), "test\31Проверка\31\31\31\31\31voice=sapi\31Привет", "with a sender's name")
print("service frames ok")

-- ShownSender: how /bv debug names a sender - no realm, no BattleTag digits
eq(ns.ShownSender("Громмаш-ПиратскаяБухта"), "Громмаш", "a character: without the realm")
eq(ns.ShownSender("Громмаш"), "Громмаш", "no realm")
eq(ns.ShownSender("BN:Вася#1234"), "BN:Вася", "a Battle.net friend: without the tag's digits")
eq(ns.ShownSender("BN:Вася"), "BN:Вася", "no digits")
eq(ns.ShownSender(""), "?", "none")
eq(ns.ShownSender(nil), "?", "none at all")
print("shown sender ok")

-- IsQuestion: a line of questions only
for _, q in ipairs({ "кто в ОП?", "танк нужен? хил?", "где? ", "что???" }) do assert(ns.IsQuestion(q), q) end
for _, s in ipairs({ "привет. кто идёт?", "ура! кто со мной?", "кто в ОП", "ну... кто?", "5.5 кто?", "ну… кто?", "" }) do
    assert(not ns.IsQuestion(s), s)
end
assert(not ns.IsQuestion(nil) and not ns.IsQuestion(5), "not a string: no")
-- letters and marks that share a byte with «…» (E2 80 A6): «р» (D1 80), «Ц» (D0 A6), «—» (E2 80 94), «№» (E2 84 96)
for _, q in ipairs({ "кто в рейд?", "Цена?", "а ты — где?", "№5 где?", "р?", "Ц?" }) do assert(ns.IsQuestion(q), q) end
print("question ok")

-- Emoticons: brackets for feelings read as a full stop, a bracket pair kept
eq(ns.Emoticons("привет)"), "привет.", "a lone bracket")
eq(ns.Emoticons("привет)))"), "привет.", "brackets in a row")
eq(ns.Emoticons("ну((("), "ну.", "opening ones")
eq(ns.Emoticons("встреча (через 5 мин) у входа"), "встреча (через 5 мин) у входа", "a pair stays")
eq(ns.Emoticons("ок :) пошли"), "ок. пошли", ":)")
eq(ns.Emoticons("ну ;-P"), "ну.", ";-P")
eq(ns.Emoticons("ну ты :Р"), "ну ты.", ":Р with a Russian Р")
eq(ns.Emoticons("ну ты :р"), "ну ты.", ":р with a Russian р")
eq(ns.Emoticons("ссылка:Dota"), "ссылка:Dota", "a letter after a colon: no smiley")
eq(ns.Emoticons("1:Сильный"), "1:Сильный", "a Russian letter after a colon")
eq(ns.Emoticons("на)(уя"), "нахуя", "a bracket pair inside a word: a masked «х»")
eq(ns.Emoticons(")(орошо"), "хорошо", "at the start")
eq(ns.Emoticons("ну }{ватит"), "ну хватит", "after a space, braces")
eq(ns.Emoticons("ура!)"), "ура!", "no full stop after «!»")
eq(ns.Emoticons("да?:)"), "да?", "nor after «?»")
print("emoticons ok")

-- Clean: the client's markup out, link names kept
eq(ns.Clean("помочь с |cffff2020|Hquest:92706:0|h[РАЗЫСКИВАЕТСЯ: Брууз]|h|r ?"), "помочь с РАЗЫСКИВАЕТСЯ: Брууз?", "a quest link")
eq(ns.Clean("продам |cff0070dd|Hitem:2589::::::::|h[Льняной мешок]|h|r"), "продам Льняной мешок", "an item link")
local link = "WTS |cnIQ1:|Hitem:250335::::::::39:1489:::1:3524::::::|h[Сильный эликсир стойкости]|h|r|cnIQ1:|Hitem:250333::::::::39:1489:::1:3524::::::|h[Сильный эликсир священника]|h|r"
eq(ns.Clean(link), "WTS Сильный эликсир стойкости Сильный эликсир священника", "links coloured by name, two in a row")
eq(ns.Clean("{rt8} стоп {череп} тут"), "стоп тут", "raid target icons")
eq(ns.Clean("|TInterface\\Icons\\INV_Misc_Bag_08:0|t сумка |A:raceicon-orc-male:16:16|a"), "сумка", "textures and atlases")
eq(ns.Clean("a || b"), "a | b", "an escaped bar")
eq(ns.Clean("танк+хил"), "танк плюс хил", "a typed «+» is the word")
eq(ns.Clean("чант +7 к урону"), "чант плюс 7 к урону", "one space each side: the dictionary's «(?<!плюс )» relies on it")
eq(ns.Clean("a\31b"), "a b", "the separator never reaches the payload")
eq(ns.Clean("  много   пробелов  "), "много пробелов", "spaces squeezed and trimmed")
eq(ns.Clean("кто , идёт ?"), "кто, идёт?", "no space before punctuation")
eq(ns.Clean("на)(уя"), "нахуя", "emoticons too")
eq(ns.Clean("привет))"), "привет.", "))")
eq(ns.Clean("ок )("), "ок.", ")(")
eq(ns.Clean("внимание:Привет"), "внимание:Привет", "a colon before a Russian letter")
eq(ns.Clean("ок :D всё"), "ок. всё", ":D")
eq(ns.Clean("ссылка:Dota"), "ссылка:Dota", "a Latin letter after a colon")
eq(ns.Clean("ну ты :Р"), "ну ты.", ":Р")
eq(ns.Clean("привет :) как"), "привет. как", ":)")
eq(ns.Clean("|cff00ff00|r"), "", "only markup: empty")
print("clean ok")

-- AddonLine: lines other players' addons write for them
local AL = ns.AddonLine
eq(AL("{звезда} Questie: Сердце Тарагамана Ненасытного: 1/1 для |cffffff00|Hquest:5761:0|h[Убить тварь]|h|r!"), "Questie", "an icon and Questie")
eq(AL("{rt1} Interrupted: Fireball"), "Interrupted", "an icon and any Latin word with a colon")
eq(AL("<DBM> Pull in 5"), "DBM", "<DBM>")
eq(AL("[Questie] accepted"), "Questie", "[Questie]")
eq(AL("Details!: Damage Done"), "Details!", "Details!:")
eq(AL("  BigWigs: Pull"), "BigWigs", "a known name with a colon, any case")
eq(AL("Полуказуальная RU/UA гильдия <MIR> ищет игроков!"), nil, "a guild tag inside a player's line")
eq(AL("[UA] Спільнота < ХАОС > запрошує"), nil, "[UA] is no addon")
eq(AL("{череп} танк: бери этого"), nil, "an icon, then Russian: a player")
eq(AL("WTS: сумки"), nil, "a Latin word with a colon that is no addon")
eq(AL("Nova: привет"), nil, "a name a character could have")
eq(AL(nil), nil, "not a string")
assert(ns.ADDON_TAGS.questie and ns.ADDON_TAGS.details and not ns.ADDON_TAGS.nova, "the tags are lowercase names")
print("addon lines ok")

-- ChannelSetting: which numbered channel setting a line falls under
local CS = ns.ChannelSetting
eq(CS("Общий", "1. Общий - Оргриммар"), "chGeneral", "Общий")
eq(CS("General"), "chGeneral", "General")
eq(CS("Торговля (локальный)", ""), "chTrade", "Торговля")
eq(CS("Trade - City"), "chTrade", "Trade")
eq(CS("Поиск спутников"), "chLfg", "Поиск спутников")
eq(CS("LookingForGroup"), "chLfg", "LookingForGroup")
eq(CS("Оборона: Оргриммар"), "chDefense", "Оборона")
eq(CS("LocalDefense"), "chDefense", "LocalDefense")
eq(CS("WorldDefense"), "chDefense", "WorldDefense")
eq(CS("Оборона мира"), "chDefense", "Оборона мира")
eq(CS("МойКанал"), "chOther", "a custom channel")
eq(CS(nil, "5. Мой"), "chOther", "a custom one by its full name")
eq(CS(nil, "2. Торговля - Степи"), "chTrade", "by the full channel name when no base name")
eq(CS("", "1. General - Durotar"), "chGeneral", "an empty base name counts as none")
eq(CS(nil, nil), "chOther", "nothing known")
print("channels ok")

-- Place: where a line was said, for «Громмаш пишет в гильдии: …»
local P = ns.Place
eq(P("party"), "в группе", "party")
eq(P("raid"), "в рейде", "raid")
eq(P("warning"), "рейду", "a raid warning: «объявляет рейду»")
eq(P("instance"), "в группе", "instance chat is a group's (a dungeon finder's or a battleground's)")
eq(P("guild"), "в гильдии", "guild")
eq(P("officer"), "в офицерском чате", "officer")
eq(P("channels", "1. Общий - Оргриммар"), "в общем", "General")
eq(P("channels", "2. Торговля - Город"), "в торговле", "Trade")
eq(P("channels", "4. LookingForGroup"), "в поиске спутников", "LookingForGroup")
eq(P("channels", "3. Оборона: Оргриммар"), "в обороне", "LocalDefense")
eq(P("channels", "5. мойканал"), "в канале мойканал", "a channel of one's own, by its name")
eq(P("channels", "6. Услуги - Город"), "в канале Услуги", "another one: without the zone")
eq(P("channels", ""), "в канале", "no name at all")
for _, kind in ipairs({ "say", "yell", "whisper", "emote", "test" }) do eq(P(kind), nil, kind .. ": the verb says it") end
print("places ok")
