-- Battle.net whispers (Core.lua ns.BNetFriend, OnChat; ChatFade.lua): read as whispers, the friend named by
-- their character in WoW or their BattleTag, never by the account's real name; one's own whispers (a
-- character's and Battle.net's) read with «Свои сообщения», as the player's; retail's secret values never touched.
-- Run: mise run test-lua (from addon/BarrensVoice, it loadfiles the addon by relative path)
local function stub()
    return setmetatable({}, { __index = function() return function() end end })
end
CreateFrame = function() return stub() end
StaticPopupDialogs, SlashCmdList, YES, NO = {}, {}, "Да", "Нет"
GetTime = function() return 0 end
UnitGUID = function() return "Player-1-1" end
UnitFullName = function() return "Джайна", "ПиратскаяБухта" end
local ns = {}
dofile("../../companion/tests/toc.lua")(ns, { "Protocol.lua", "DictionaryOnline.lua", "Dictionary.lua", "Text.lua",
    "QuestVoice.lua", "Core.lua", "ChatFade.lua" })
ns.db = {}
for k, v in pairs(ns.DEFAULTS) do ns.db[k] = v end
ns.db.onlyVisible, ns.db.waitForCatQuest, ns.db.sayWhere = false, false, false
local sent = {}
ns.Strip = { Push = function(p) sent[#sent + 1] = p end }

local REAL = "Иван Настоящий"   -- the account's real name: never said, sent or logged
local TOKEN = "|Kq7|k"          -- the event's playerName: a token the chat shows as that real name
local friends = {
    [7] = { accountName = REAL, battleTag = "Вася#1234", gameAccountInfo = { clientProgram = "WoW",
        characterName = "Громмаш", realmName = "Пиратская Бухта", playerGuid = "Player-1-77" } },
    [8] = { accountName = REAL, battleTag = "Тиранда#2345", gameAccountInfo = { clientProgram = "App" } },
    [9] = { accountName = REAL, battleTag = "Брэнн#3456", gameAccountInfo = { clientProgram = "WoW" } },   -- in the menus
    -- in another game that has characters too: not a WoW character, the BattleTag
    [13] = { accountName = REAL, battleTag = "Кейн#5678", gameAccountInfo = { clientProgram = "WTCG",
        characterName = "Чужой", realmName = "Где-то", playerGuid = "Player-1-77" } },
}
C_BattleNet = { GetAccountInfoByID = function(id) return friends[id] end }
BNET_CLIENT_WOW = "WoW"
GetPlayerInfoByGUID = function(guid)
    if guid == "Player-1-77" then return "Воин", "WARRIOR", "Орк", "Orc", 2, "Громмаш", "ПиратскаяБухта" end
    if guid == "Player-1-1" then return "Маг", "MAGE", "Человек", "Human", 3, "Джайна", "ПиратскаяБухта" end
    if guid == "Player-1-5" then return "Жрец", "PRIEST", "Ночная эльфийка", "NightElf", 3, "Тиранда", "" end
end

local function whisper(text, id, event)
    sent = {}
    ns.OnEvent(event or "CHAT_MSG_BN_WHISPER", text, TOKEN, "", "", TOKEN, "", 0, 0, "", 0, 1, "", id, false)
    return sent
end
local function fields(p)
    local f = {}
    for x in (p .. "\31"):gmatch("(.-)\31") do f[#f + 1] = x end
    return f
end
local function private(p)
    assert(not p:find(REAL, 1, true) and not p:find("|K", 1, true), "the real name got out: " .. p)
end

assert(ns.EVENTS.CHAT_MSG_BN_WHISPER == "whisper", "read under «Шёпот»")
assert(ns.EVENTS.CHAT_MSG_BN_WHISPER_INFORM == "whisper" and ns.EVENTS.CHAT_MSG_WHISPER_INFORM == "whisper",
    "one's own whispers, a character's and Battle.net's, under «Шёпот» too")

-- a friend in WoW: their character's name (no realm), the voice of their race and sex
local f = fields(whisper("привет, идёшь в ОП?", 7)[1])
assert(f[1] == "whisper" and f[2] == "Громмаш-ПиратскаяБухта", f[1] .. " " .. f[2])
assert(f[3] == "Orc" and f[4] == "2" and f[5] == "WARRIOR", "race and sex by the GUID: " .. f[3] .. " " .. f[4])
assert(f[8] == "Громмаш шепчет:\4 привет, идёшь в ОП?", f[8])
private(sent[1])
print("friend in WoW ok")

-- a friend in the Battle.net app: the BattleTag without "#1234", no race (the companion's default voice)
f = fields(whisper("ты где?", 8)[1])
assert(f[2] == "BN:Тиранда#2345" and f[3] == "" and f[4] == "", f[2] .. " " .. f[3] .. " " .. f[4])
assert(f[8] == "Тиранда шепчет:\4 ты где?", f[8])
private(sent[1])
-- in WoW with no character yet: the BattleTag as well
f = fields(whisper("я тут", 9)[1])
assert(f[2] == "BN:Брэнн#3456" and f[8] == "Брэнн шепчет:\4 я тут", f[2] .. " " .. f[8])
print("friend in the app ok")

-- /bv last: the friend named as before
sent = {}
ns.Replay(3)
assert(#sent == 3 and fields(sent[1])[8] == "Громмаш шепчет:\4 привет, идёшь в ОП?" and fields(sent[2])[8]:find("^Тиранда"),
    sent[1] or "nothing replayed")
-- the history (saved variables, on disk) keeps a BattleTag without its digits; a character's sender whole
for _, h in ipairs(ns.history) do assert(not tostring(h[2]):find("#", 1, true), "digits at rest: " .. tostring(h[2])) end
assert(ns.history[#ns.history - 1][2] == "BN:Тиранда" and ns.history[#ns.history - 2][2] == "Громмаш-ПиратскаяБухта",
    tostring(ns.history[#ns.history - 1][2]))
assert(fields(sent[2])[2] == "BN:Тиранда", "replayed so: " .. fields(sent[2])[2])
print("replay ok")
f = fields(whisper("го в арену", 13)[1])
assert(f[2] == "BN:Кейн#5678" and f[3] == "" and f[8] == "Кейн шепчет:\4 го в арену", "another game: " .. f[2] .. " " .. f[8])

-- not told: no answer, an error, no such API - not read, and /bv debug names no one
ns.db.debug = true
for _, id in ipairs({ 99, "7", nil }) do
    whisper("кто я?", id)
    assert(#sent == 1 and fields(sent[1])[1] == "diag", "only the debug note: " .. tostring(id))
    private(sent[1])
end
C_BattleNet.GetAccountInfoByID = function() error("no") end
whisper("кто я?", 7)
assert(#sent == 1 and fields(sent[1])[1] == "diag")
C_BattleNet.GetAccountInfoByID = function(id) return friends[id] end
-- «Шёпот» off: not read, and the note says no real name either, nor the BattleTag's digits
ns.db.whisper = false
whisper("привет", 7)
assert(#sent == 1 and fields(sent[1])[1] == "diag", sent[1] or "nothing")
private(sent[1])
whisper("привет", 8)
assert(#sent == 1 and sent[1]:find("BN:Тиранда:", 1, true) and not sent[1]:find("2345", 1, true), sent[1])
ns.db.whisper, ns.db.debug = true, false
assert(#whisper("привет", 7) == 1, "on again")
print("unknown friend ok")

-- one's own whispers (the _INFORM events): their name, GUID and bnSenderID are the recipient's - the line is
-- the player's, read only with «Свои сообщения»; the recipient is never named
local function own(event, text, id)
    sent = {}
    -- to Тиранда (a character: name and GUID) or to friend 7 (Battle.net: the real name's token, bnSenderID)
    local to, guid = event == "CHAT_MSG_WHISPER_INFORM" and "Тиранда-ПиратскаяБухта" or TOKEN,
        event == "CHAT_MSG_WHISPER_INFORM" and "Player-1-5" or ""
    ns.OnEvent(event, text, to, "", "", to, "", 0, 0, "", 0, 1, guid, id or 0, false)
    return sent
end
local lookups = 0
local lookup = C_BattleNet.GetAccountInfoByID
C_BattleNet.GetAccountInfoByID = function(id) lookups = lookups + 1 return lookup(id) end
-- before the player has written a line the game's sender for them is not known (on Forever UnitFullName's second
-- result may be the surname, not the realm): one's own whisper is not read, /bv debug says why and names no one
local fullName = UnitFullName
UnitFullName = function() error("one's own sender is never built from UnitFullName") end
ns.db.self, ns.db.debug = true, true
for _, event in ipairs({ "CHAT_MSG_WHISPER_INFORM", "CHAT_MSG_BN_WHISPER_INFORM" }) do
    own(event, "рано", 7)
    assert(#sent == 1 and fields(sent[1])[1] == "diag" and sent[1]:find("твоё имя в чате ещё не известно", 1, true)
        and sent[1]:find(": ты: рано", 1, true), "not known yet: not read - " .. tostring(sent[1]))
    private(sent[1])
    assert(not sent[1]:find("Тиранда", 1, true) and not sent[1]:find("Громмаш", 1, true), "the recipient unnamed")
end
assert(ns.ChatFade.Verdict("Для [Тиранда]: рано", "CHAT_MSG_WHISPER_INFORM", { "рано", "Тиранда-ПиратскаяБухта", "", "",
    "Тиранда-ПиратскаяБухта", "", 0, 0, "", 0, 1, "Player-1-5", 0, false, n = 14 }) == "skipped",
    "not read: the hidden chat shows it")
-- a line of the player's own tells it - one in a channel switched off too
ns.db.say = false
ns.OnEvent("CHAT_MSG_SAY", "привет", "Джайна-ПиратскаяБухта", "", "", "Джайна-ПиратскаяБухта", "", 0, 0, "", 0, 1,
    "Player-1-1", 0, false)
ns.db.say = true
assert(ns.PlayerSender() == "Джайна-ПиратскаяБухта" and ns.db.ownSender["Player-1-1"] == "Джайна-ПиратскаяБухта",
    "kept by the character's GUID in the saved variables")
ns.db.self = false
for _, event in ipairs({ "CHAT_MSG_WHISPER_INFORM", "CHAT_MSG_BN_WHISPER_INFORM" }) do
    own(event, "я отправил", 7)
    assert(#sent == 1 and fields(sent[1])[1] == "diag" and sent[1]:find("свои сообщения выключены", 1, true)
        and sent[1]:find("Джайна", 1, true) and not sent[1]:find("Тиранда", 1, true),
        "self off: not read, the note names the player: " .. tostring(sent[1]))
    private(sent[1])
end
ns.db.self, ns.db.debug = true, false
f = fields(own("CHAT_MSG_WHISPER_INFORM", "иду")[1])
assert(f[1] == "whisper" and f[2] == "Джайна-ПиратскаяБухта", "the player is the sender: " .. f[2])
assert(f[3] == "Human" and f[4] == "3" and f[5] == "MAGE", "the player's race and sex: " .. f[3] .. " " .. f[4])
assert(f[8] == "Джайна шепчет:\4 иду", "no recipient, no place: " .. f[8])
f = fields(own("CHAT_MSG_BN_WHISPER_INFORM", "ты где?", 7)[1])
assert(f[2] == "Джайна-ПиратскаяБухта" and f[3] == "Human" and f[4] == "3", "Battle.net: the player too " .. f[2])
assert(f[8] == "Джайна шепчет:\4 ты где?", "the verb stays for a question, no recipient: " .. f[8])
assert(not sent[1]:find("Громмаш", 1, true) and not sent[1]:find("Вася", 1, true), "the recipient unnamed")
private(sent[1])
assert(lookups == 0, "the recipient's bnSenderID is never looked up")
C_BattleNet.GetAccountInfoByID = lookup
-- the game's latest sender for the player wins: the same voice as their other lines
ns.OnEvent("CHAT_MSG_SAY", "привет", "Джайна", "", "", "Джайна", "", 0, 0, "", 0, 1, "Player-1-1", 0, false)
assert(fields(own("CHAT_MSG_WHISPER_INFORM", "иду")[1])[2] == "Джайна", "as the say line's sender")
-- another character (the saved variables are the account's): theirs is not known yet
UnitGUID = function() return "Player-1-9" end
assert(#own("CHAT_MSG_WHISPER_INFORM", "иду") == 0, "another character's whisper waits for their own line")
UnitGUID = function() return "Player-1-1" end
UnitFullName = fullName
-- «Шёпот» off: one's own not read either
ns.db.whisper = false
assert(#own("CHAT_MSG_WHISPER_INFORM", "иду") == 0 and #own("CHAT_MSG_BN_WHISPER_INFORM", "иду", 7) == 0)
ns.db.whisper = true
print("own whispers ok")

-- «Что читать»: the windows that show Battle.net whispers (the chat's message group BN_WHISPER)
ChatTypeGroupInverted = { CHAT_MSG_BN_WHISPER = "BN_WHISPER", CHAT_MSG_BN_WHISPER_INFORM = "BN_WHISPER",
    CHAT_MSG_WHISPER = "WHISPER", CHAT_MSG_WHISPER_INFORM = "WHISPER" }
NUM_CHAT_WINDOWS = 1
ChatFrame1 = { messageTypeList = { "SAY", "WHISPER" } }
GetChatWindowInfo = function() return "Общий", 14, 1, 1, 1, 1, true, false, 1 end
ns.db.onlyVisible, ns.db.debug = true, true
assert(#whisper("привет", 7) == 1 and fields(sent[1])[1] == "diag", "no window shows Battle.net whispers: not read")
-- /bv debug names the friend by no token: «друг Battle.net»
assert(sent[1]:find("нет открытого окна чата", 1, true) and sent[1]:find(": друг Battle.net: привет", 1, true), sent[1])
private(sent[1])
ns.db.debug = false
ChatFrame1.messageTypeList[3] = "BN_WHISPER"
assert(#whisper("привет", 7) == 1, "a window shows them: read")
ChatFrame1.messageTypeList = { "SAY", "BN_WHISPER" }
assert(#own("CHAT_MSG_WHISPER_INFORM", "иду") == 0, "one's own whisper: by the windows' WHISPER group")
assert(#own("CHAT_MSG_BN_WHISPER_INFORM", "иду", 7) == 1, "one's own Battle.net whisper: BN_WHISPER")
ChatFrame1.messageTypeList = { "SAY", "WHISPER" }
assert(#own("CHAT_MSG_WHISPER_INFORM", "иду") == 1 and #own("CHAT_MSG_BN_WHISPER_INFORM", "иду", 7) == 0)
ns.db.onlyVisible = false
print("visible ok")

-- the hidden chat: a Battle.net whisper read aloud keeps it hidden unless «шёпот» shows it; one's own shows it
local V = ns.ChatFade.Verdict
local function args(id) return { "привет", TOKEN, "", "", TOKEN, "", 0, 0, "", 0, 1, "", id, false, n = 14 } end
assert(V("[" .. TOKEN .. "] шепчет: привет", "CHAT_MSG_BN_WHISPER", args(7)) == "read")
assert(ns.ChatFade.ALWAYS_SHOW.CHAT_MSG_BN_WHISPER == "fadeWhisper", "shown with «шёпот»")
-- a friend who cannot be told: not read (OnChat drops it), so the hidden chat shows it
for _, id in ipairs({ 99, "7", false }) do
    assert(V("[" .. TOKEN .. "] шепчет: привет", "CHAT_MSG_BN_WHISPER", args(id)) == "skipped", tostring(id))
end
C_BattleNet.GetAccountInfoByID = function() error("no") end
assert(V("x", "CHAT_MSG_BN_WHISPER", args(7)) == "skipped", "the lookup fails: shown")
C_BattleNet.GetAccountInfoByID = function(id) return friends[id] end
-- one's own whispers: read with «Свои сообщения» (then shown only with «шёпот»), else shown
local function informArgs(event)
    if event == "CHAT_MSG_BN_WHISPER_INFORM" then return args(7) end
    return { "привет", "Тиранда", "", "", "Тиранда", "", 0, 0, "", 0, 1, "Player-1-5", 0, false, n = 14 }
end
for _, event in ipairs({ "CHAT_MSG_WHISPER_INFORM", "CHAT_MSG_BN_WHISPER_INFORM" }) do
    assert(V("Для [x]: привет", event, informArgs(event)) == "read", event .. ": read")
    assert(ns.ChatFade.ALWAYS_SHOW[event] == "fadeWhisper", event .. ": shown with «шёпот»")
    ns.db.self = false
    assert(V("Для [x]: привет", event, informArgs(event)) == "skipped", event .. ": self off, shown")
    ns.db.self = true
end
ns.db.whisper = false
assert(V("x", "CHAT_MSG_BN_WHISPER", args(7)) == "skipped", "«Шёпот» off: shown")
ns.db.whisper = true
print("hidden chat ok")

-- retail's closed chat: secret values dropped before anything looks at them
local SECRET = setmetatable({}, { __tostring = function() error("a secret value cannot be read") end,
    __index = function() error("a secret value cannot be read") end,
    __concat = function() error("a secret value cannot be read") end,
    __eq = function() error("a secret value cannot be compared") end })
issecretvalue = function(v) return rawequal(v, SECRET) end
local told, print0 = {}, print
print = function(t) told[#told + 1] = t end
sent = {}
ns.OnEvent("CHAT_MSG_BN_WHISPER", SECRET, SECRET, "", "", SECRET, "", 0, 0, "", 0, 1, SECRET, SECRET, false)
assert(#sent == 0 and #told == 1, "a secret line: not read, the player told once")
assert(#whisper("привет", SECRET) == 0, "a secret bnSenderID alone: not read")
friends[10] = { accountName = REAL, battleTag = SECRET, gameAccountInfo = { clientProgram = "App" } }
assert(#whisper("привет", 10) == 0, "a secret BattleTag: not read")
friends[11] = { battleTag = "Джайна#4567", gameAccountInfo = { clientProgram = "WoW", characterName = SECRET } }
f = fields(whisper("привет", 11)[1])
assert(f[2] == "BN:Джайна#4567", "a secret character name: the BattleTag " .. f[2])
friends[12] = SECRET
assert(#whisper("привет", 12) == 0, "a secret answer: not read")
GetPlayerInfoByGUID = function() return SECRET, SECRET, SECRET, SECRET, SECRET end
f = fields(whisper("привет", 7)[1])
assert(f[2] == "Громмаш-ПиратскаяБухта" and f[3] == "" and f[4] == "", "secret race and sex: none " .. f[3])
assert(V("x", "CHAT_MSG_BN_WHISPER", args(SECRET)) == "closed", "the hidden chat: closed")
-- one's own whisper in the closed chat: dropped, the recipient's bnSenderID not even looked at
local lookups = 0
C_BattleNet.GetAccountInfoByID = function() lookups = lookups + 1 end
for _, event in ipairs({ "CHAT_MSG_WHISPER_INFORM", "CHAT_MSG_BN_WHISPER_INFORM" }) do
    sent = {}
    ns.OnEvent(event, SECRET, SECRET, "", "", SECRET, "", 0, 0, "", 0, 1, SECRET, SECRET, false)
    assert(#sent == 0, event .. ": a secret one not read")
    local closed = { SECRET, SECRET, "", "", SECRET, "", 0, 0, "", 0, 1, SECRET, SECRET, false, n = 14 }
    assert(V("x", event, closed) == "closed", event .. ": the hidden chat shows it")
end
assert(lookups == 0, "no lookup for a secret own whisper")
C_BattleNet.GetAccountInfoByID = function(id) return friends[id] end
-- /bv debug's line on the window shown (one's own Battle.net whisper, not read): the friend's token not in it
ns.db.fadeChat, ns.db.debug, ns.db.self = true, true, false
ns.Companion = { State = function() return "running" end }
local frame = { AddMessage = function() end }
CHAT_FRAMES, ChatFrame1 = { "ChatFrame1" }, frame
hooksecurefunc = function(t, name, f)
    local orig = t[name]
    t[name] = function(...) orig(...) f(...) end
end
ns.ChatFade.Initialize()
ns.ChatFade.Reveal = function() return true end
sent = {}
frame:AddMessage("|HBNplayer:" .. TOKEN .. ":7:1:BN_WHISPER:" .. TOKEN .. "|h[" .. TOKEN .. "]|h: я отправил", 1, 1, 1, 1, 1, 1,
    "CHAT_MSG_BN_WHISPER_INFORM", args(7))
assert(#sent == 1 and sent[1]:find("я отправил", 1, true), sent[1] or "no debug line")
private(sent[1])
sent = {}
frame:AddMessage("[|Kq7]: без конца", 1, 1, 1, 1, 1, 1, "CHAT_MSG_BN_WHISPER_INFORM", args(7))
private(sent[1])
ns.db.self = true
print = print0
issecretvalue = nil
print("secret ok")
