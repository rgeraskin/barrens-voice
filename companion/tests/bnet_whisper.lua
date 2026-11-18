-- Battle.net whispers (Core.lua ns.BNetFriend, OnChat; ChatFade.lua): read as whispers, the friend named by
-- their character in WoW or their BattleTag, never by the account's real name; one's own not read; retail's
-- secret values never touched.
-- Run: mise run test-lua (from addon/BarrensVoice, it loadfiles the addon by relative path)
local function stub()
    return setmetatable({}, { __index = function() return function() end end })
end
CreateFrame = function() return stub() end
StaticPopupDialogs, SlashCmdList, YES, NO = {}, {}, "Да", "Нет"
GetTime = function() return 0 end
UnitGUID = function() return "Player-1-1" end
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
}
C_BattleNet = { GetAccountInfoByID = function(id) return friends[id] end }
BNET_CLIENT_WOW = "WoW"
GetPlayerInfoByGUID = function(guid)
    if guid == "Player-1-77" then return "Воин", "WARRIOR", "Орк", "Orc", 2, "Громмаш", "ПиратскаяБухта" end
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
assert(ns.EVENTS.CHAT_MSG_BN_WHISPER_INFORM == nil and ns.EVENTS.CHAT_MSG_WHISPER_INFORM == nil,
    "one's own whispers are not read, a character's or Battle.net's")

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
print("replay ok")

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
-- «Шёпот» off: not read, and the note says no name either
ns.db.whisper = false
whisper("привет", 7)
assert(#sent == 1 and fields(sent[1])[1] == "diag", sent[1] or "nothing")
private(sent[1])
ns.db.whisper, ns.db.debug = true, false
assert(#whisper("привет", 7) == 1, "on again")
print("unknown friend ok")

-- one's own Battle.net whisper (the _INFORM event), like a character's: not read, «Свои сообщения» or not
for _, own in ipairs({ false, true }) do
    ns.db.self = own
    assert(#whisper("я отправил", 7, "CHAT_MSG_BN_WHISPER_INFORM") == 0, "own Battle.net whisper, self " .. tostring(own))
    assert(#whisper("я отправил", 7, "CHAT_MSG_WHISPER_INFORM") == 0, "own whisper, self " .. tostring(own))
end
ns.db.self = true
print("own whispers ok")

-- «Что читать»: the windows that show Battle.net whispers (the chat's message group BN_WHISPER)
ChatTypeGroupInverted = { CHAT_MSG_BN_WHISPER = "BN_WHISPER", CHAT_MSG_BN_WHISPER_INFORM = "BN_WHISPER",
    CHAT_MSG_WHISPER = "WHISPER" }
NUM_CHAT_WINDOWS = 1
ChatFrame1 = { messageTypeList = { "SAY", "WHISPER" } }
GetChatWindowInfo = function() return "Общий", 14, 1, 1, 1, 1, true, false, 1 end
ns.db.onlyVisible = true
assert(#whisper("привет", 7) == 0, "no window shows Battle.net whispers: not read")
ChatFrame1.messageTypeList[3] = "BN_WHISPER"
assert(#whisper("привет", 7) == 1, "a window shows them: read")
ns.db.onlyVisible = false
print("visible ok")

-- the hidden chat: a Battle.net whisper read aloud keeps it hidden unless «шёпот» shows it; one's own shows it
local V = ns.ChatFade.Verdict
local function args(id) return { "привет", TOKEN, "", "", TOKEN, "", 0, 0, "", 0, 1, "", id, false, n = 14 } end
assert(V("[" .. TOKEN .. "] шепчет: привет", "CHAT_MSG_BN_WHISPER", args(7)) == "read")
assert(ns.ChatFade.ALWAYS_SHOW.CHAT_MSG_BN_WHISPER == "fadeWhisper", "shown with «шёпот»")
assert(V("Для [" .. TOKEN .. "]: привет", "CHAT_MSG_BN_WHISPER_INFORM", args(7)) == "skipped", "one's own: shown")
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
-- /bv debug's line on the window shown: the friend's token not in it
ns.db.fadeChat, ns.db.debug = true, true
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
print = print0
issecretvalue = nil
print("secret ok")
