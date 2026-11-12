-- Minimal WoW API stubs: run the addon's files and open every window, to catch nil calls and typos.
local function widget()
    local w = { _text = "", _shown = false, _checked = false, _scripts = {} }
    return setmetatable(w, { __index = function(t, k)
        if k == "GetText" then return function(self) return self._text end end
        if k == "SetText" then return function(self, v) self._text = v or "" end end
        if k == "GetHeight" or k == "GetWidth" or k == "GetStringWidth" then return function() return 100 end end
        if k == "GetChecked" then return function(self) return self._checked end end
        if k == "SetChecked" then return function(self, v) self._checked = v end end
        if k == "IsShown" then return function(self) return self._shown end end
        if k == "SetShown" then return function(self, v) self._shown = v; if v and self._scripts.OnShow then self._scripts.OnShow(self) end end end
        if k == "Show" then return function(self) self:SetShown(true) end end
        if k == "Hide" then return function(self)
            if self._shown and self._scripts.OnHide then self._scripts.OnHide(self) end
            self._shown = false
        end end
        if k == "SetScript" then return function(self, n, f) self._scripts[n] = f end end
        if k == "GetScript" then return function(self, n) return self._scripts[n] end end
        if k == "GetValue" then return function(self) return self._value or 100 end end
        if k == "SetValue" then return function(self, v)
            self._value = v
            if self._scripts.OnValueChanged then self._scripts.OnValueChanged(self, v) end
        end end
        if k:match("^Create") then return function() return widget() end end
        return function() end
    end })
end
local frames = {}
CreateFrame = function() local f = widget(); frames[#frames + 1] = f; return f end
UIParent, WorldFrame, Minimap, GameTooltip = widget(), widget(), widget(), widget()
UISpecialFrames, SlashCmdList, StaticPopupDialogs = {}, {}, {}
StaticPopup_Show = function() end
YES, NO = "Да", "Нет"
tinsert = table.insert
GameTooltip_Hide = function() end
GetPhysicalScreenSize = function() return 2360, 1640 end
GetTime = function() return 0 end
UnitGUID = function() return "me" end
BackdropTemplateMixin = {}
C_Timer = { NewTimer = function(_, f) return { Cancel = function() end } end, NewTicker = function() end,
            After = function(_, f) f() end }
Settings = { RegisterCanvasLayoutCategory = function() return {} end, RegisterAddOnCategory = function() end }
local ns = {}
for _, f in ipairs({ "Protocol.lua", "Strip.lua", "Dictionary.lua", "VoiceList.lua", "Core.lua", "UI.lua",
                     "DictionaryWindow.lua", "StripWindow.lua", "Options.lua", "VoicesWindow.lua", "Minimap.lua" }) do
    assert(loadfile(f))("WowChatVoice", ns)
end
WowChatVoiceVoiceList = { { name = "Anna", label = "Anna (RHVoice)", gender = "Female", on = true },
                          { name = "Aidar (Russian)", label = "Aidar (Silero)", gender = "Male", on = true } }
ns.db = setmetatable({ rate = 100, voices = "f5", enabled = true,
                       sayNames = true, sayVerb = true, minimapIcon = true }, {})
ns.Dictionary.Migrate(ns.db)
ns.Dictionary.Rebuild()
local sent = {}
ns.Strip.Push = function(p) sent[#sent + 1] = p end
ns.Options.Initialize()
ns.db.volume = 150
ns.Options.Toggle(); assert(ns.db.volume == 150 and ns.db.rate == 100, "Refresh must keep the settings")
print("options ok")
ns.DictionaryWindow.Toggle(); print("dictionary ok")
ns.VoicesWindow.Toggle(); print("voices ok")
ns.Minimap.Update(); print("minimap ok")
ns.Send("say", "Ивар Седой-Степи", "Orc", 3, "WARRIOR", "", "всем привет")
ns.db.sayLastNames = true
ns.Send("say", "Ивар Седой-Степи", "Orc", 3, "WARRIOR", "", "и фамилия")
ns.db.sayLastNames = false
ns.Send("yell", "Вася-Степи", "Orc", 2, "WARRIOR", "", "АААА")
ns.Send("emote", "Вася-Степи", "Orc", 2, "WARRIOR", "", "смеётся")
ns.db.sayVerb = false
ns.Send("party", "Вася-Степи", "Orc", 2, "WARRIOR", "", "го")
for _, p in ipairs(sent) do print((p:gsub("\31", " | "):gsub("[\2\3]", ""))) end

-- Only what the chat windows show: window 1 is open (say, party, the zone channel "Общий"),
-- window 2 (guild) is closed, and a chat filter hides lines with "спам".
NUM_CHAT_WINDOWS = 2
ChatFrame1 = { messageTypeList = { "SAY", "PARTY" }, channelList = { "Общий" }, zoneChannelList = { 1 } }
ChatFrame2 = { messageTypeList = { "GUILD" }, channelList = {}, zoneChannelList = {} }
GetChatWindowInfo = function(i)
    if i == 1 then return "Общий", 14, 1, 1, 1, 1, true, false, 1 end
    return "Гильдия", 14, 1, 1, 1, 1, false, false, nil
end
ChatFrame_GetMessageEventFilters = function() return { function(_, _, msg) return msg:find("спам") ~= nil end } end
for k, v in pairs({ say = true, yell = true, guild = true, channels = true, onlyVisible = true, sayNames = false }) do
    ns.db[k] = v
end
local loader
for _, f in ipairs(frames) do
    if f._scripts.OnEvent and not loader then loader = f end
end
local function fire(event, msg, zoneId, base)
    sent = {}
    ns.Strip.Push = function(p) sent[#sent + 1] = p end
    loader._scripts.OnEvent(loader, event, msg, "Вася-Степи", "", base and ("1. " .. base) or "", "", "", zoneId or 0,
        0, base or "", nil, 1, "")
    return #sent == 1
end
local cases = {
    { "CHAT_MSG_SAY", "привет", nil, nil, true },
    { "CHAT_MSG_YELL", "кричу", nil, nil, false },             -- no window takes yells
    { "CHAT_MSG_GUILD", "гильдия", nil, nil, false },          -- its window is closed
    { "CHAT_MSG_CHANNEL", "в общем", 1, "Общий", true },
    { "CHAT_MSG_CHANNEL", "в торговле", 0, "Торговля", false }, -- not in any window
    { "CHAT_MSG_SAY", "это спам", nil, nil, false },           -- hidden by a chat filter
}
for _, c in ipairs(cases) do
    assert(fire(c[1], c[2], c[3], c[4]) == c[5], c[1] .. " " .. c[2])
end
ns.db.onlyVisible = false
assert(fire("CHAT_MSG_YELL", "кричу"), "everything when the option is off")
print("visible ok")

-- quest and item links read as their names; a bracket pair inside a word is a masked "х"
assert(ns.Clean("помочь с |cffff2020|Hquest:92706:0|h[РАЗЫСКИВАЕТСЯ: Брууз]|h|r ?") == "помочь с РАЗЫСКИВАЕТСЯ: Брууз?",
    ns.Clean("помочь с |cffff2020|Hquest:92706:0|h[РАЗЫСКИВАЕТСЯ: Брууз]|h|r ?"))
assert(ns.Clean("продам |cff0070dd|Hitem:2589::::::::|h[Льняной мешок]|h|r") == "продам Льняной мешок")
assert(ns.Clean("на)(уя") == "нахуя", ns.Clean("на)(уя"))
assert(ns.Clean(")(орошо") == "хорошо" and ns.Clean("ну }{ватит") == "ну хватит")
assert(ns.Clean("привет))") == "привет." and ns.Clean("ок )(") == "ок.", ns.Clean("ок )("))
-- a link coloured by name (|cnIQ1:), and a colon before a Russian letter left whole
local link = "WTS |cnIQ1:|Hitem:250335::::::::39:1489:::1:3524::::::|h[Сильный эликсир стойкости]|h|r|cnIQ1:|Hitem:250333::::::::39:1489:::1:3524::::::|h[Сильный эликсир священника]|h|r"
assert(ns.Clean(link) == "WTS Сильный эликсир стойкости Сильный эликсир священника", ns.Clean(link))
assert(ns.Clean("внимание:Привет") == "внимание:Привет", ns.Clean("внимание:Привет"))
assert(ns.Clean("ссылка:Dota") == "ссылка:Dota", ns.Clean("ссылка:Dota"))
assert(ns.Clean("ну ты :Р") == "ну ты.", ns.Clean("ну ты :Р"))
assert(ns.Clean("ок :D всё") == "ок. всё", ns.Clean("ок :D всё"))
assert(ns.Clean("привет :) как") == "привет. как", ns.Clean("привет :) как"))
print("clean ok")
-- the dictionary is the program's now: the addon sends the line as typed (cleaned) and the player's
-- layer of the dictionary as "dict" frames
sent = {}
ns.Strip.Push = function(p) sent[#sent + 1] = p end
ns.db.sayNames = false
ns.Send("party", "Вася-Степи", "Orc", 2, "WARRIOR", "", "кто в ОП")
assert(sent[1]:find("\31кто в ОП\31", 1, true), sent[1])
sent = {}
ns.SendDictionary(true)
assert(#sent >= 1 and sent[1]:find("^dict\31"), sent[1] or "nothing sent")
print("dictionary to the program ok")

-- while CatQuest reads a quest, chat lines wait; they go when it is done; stale ones are dropped
local clock = 100
GetTime = function() return clock end
CatQuestCore = { state = { playing = true } }
sent = {}
ns.Strip.Push = function(p) sent[#sent + 1] = p end
ns.db.waitForCatQuest = true
ns.Send("party", "Вася-Степи", "Orc", 2, "WARRIOR", "", "первая")
assert(#sent == 0, "held while CatQuest speaks")
clock = 105
ns.Send("party", "Вася-Степи", "Orc", 2, "WARRIOR", "", "вторая")
ns.ReleaseHeld()
assert(#sent == 0, "still held")
CatQuestCore.state.playing = false
clock = 142                                   -- the first waited 42 s: dropped; the second 37 s: sent
ns.ReleaseHeld()
local chat, diag = {}, {}
for _, p in ipairs(sent) do
    if p:find("^diag\31") then diag[#diag + 1] = p else chat[#chat + 1] = p end
end
assert(#chat == 1 and chat[1]:find("вторая"), "only the fresh one goes: " .. #chat)
assert(#diag == 1 and diag[1]:find("CatQuest"), "the dropped one is reported to the program's log")
sent = { chat[1] }
ns.Send("party", "Вася-Степи", "Orc", 2, "WARRIOR", "", "третья")
assert(#sent == 2, "CatQuest silent: straight to the strip")
CatQuestCore.state = { playing = true, startedAt = 200, duration = 10 }
clock = 205
ns.Send("party", "Вася-Степи", "Orc", 2, "WARRIOR", "", "пока трек")
assert(#sent == 2, "held while the track plays")
clock = 214                                   -- 4 s past its 10 s: "playing" is stuck, the chat goes on
ns.Send("party", "Вася-Степи", "Orc", 2, "WARRIOR", "", "после трека")
ns.ReleaseHeld()
assert(#sent == 4, "a stuck CatQuest does not hold the chat: " .. #sent)
CatQuestCore.state = { playing = false }
-- debug: CatQuest's speech and a held line noted in the program's log
ns.db.debug = true
sent = {}
local first = {}
ns.Strip.PushFirst = function(p) first[#first + 1] = p end
ns.WatchCatQuest()
assert(#sent == 0, "silent CatQuest, nothing to note at first")
assert(#first == 1 and first[1]:find("^resume\31"), "the first check tells the program the state")
CatQuestCore.state = { playing = true, source = "pack", startedAt = 300, duration = 34 }
clock = 301
ns.WatchCatQuest()
assert(sent[1] and sent[1]:find("^diag\31") and sent[1]:find("играет: pack, 34 с — чат ждёт", 1, true), sent[1] or "nothing")
assert(#first == 2 and first[2]:find("^pause\31"), "CatQuest speaks: the program pauses, ahead of the queue")
ns.WatchCatQuest()
assert(#first == 2, "a pause is sent once")
ns.Send("party", "Вася-Степи", "Orc", 2, "WARRIOR", "", "в очередь")
assert(sent[2]:find("строка ждёт CatQuest", 1, true), sent[2] or "nothing")
CatQuestCore.state = { playing = false }
ns.WatchCatQuest()
ns.ReleaseHeld()
assert(sent[3]:find("CatQuest замолчал", 1, true) and sent[4]:find("в очередь", 1, true), tostring(sent[3]))
assert(#first == 3 and first[3]:find("^resume\31"), "CatQuest silent: the program goes on")
ns.Skip("свои сообщения выключены", "Вася-Степи", "|cff00ff00привет|r")
assert(sent[5]:find("не отправлено (свои сообщения выключены): Вася: привет", 1, true), sent[5])
ns.Send("party", "Вася-Степи", "Orc", 2, "WARRIOR", "", "   ")
assert(sent[6]:find("пусто после очистки", 1, true), sent[6] or "nothing")
ns.db.debug = false
ns.Skip("x", "a", "b")
assert(#sent == 6, "no notes with debug off")
sent = { 1, 2, 3, 4 }
CatQuestCore = nil
ns.Send("party", "Вася-Степи", "Orc", 2, "WARRIOR", "", "без CatQuest")
assert(#sent == 5, "no CatQuest: straight to the strip")
GetTime = function() return 0 end
print("catquest ok")

-- the name is followed by a mark (\4): the program drops it when the same character goes on
ns.db.sayNames, ns.db.sayVerb, ns.db.waitForCatQuest = true, true, true
sent = {}
ns.Strip.Push = function(p) sent[#sent + 1] = p end
local function said(i)
    local fields = {}
    for f in (sent[i] .. "\31"):gmatch("(.-)\31") do fields[#fields + 1] = f end
    return (fields[8]:gsub("[\2\3]", ""))
end
ns.Send("party", "Вася-Степи", "Orc", 2, "WARRIOR", "", "привет")
ns.Send("emote", "Вася-Степи", "Orc", 2, "WARRIOR", "", "смеётся")
assert(said(1) == "Вася пишет:\4 привет", said(1))
assert(said(2) == "Вася\5 смеётся", said(2))                               -- an emote: a name never dropped
print("continue ok")

-- where the strip goes: the top (default), the bottom, or a place of one's own kept on the screen
ns.db.cell, ns.db.rows = 2, 1
local gx, gy, gw, gh = ns.Strip.Geometry("top")
assert(gx == 0 and gy == 0 and gw == 2360 and gh == 2, "top")
gx, gy, gw, gh = ns.Strip.Geometry("bottom")
assert(gx == 0 and gy == 1638 and gw == 2360, "bottom: " .. gy)
gx, gy, gw = ns.Strip.Geometry("custom", 2300, 5000, 100)
assert(gw == 200 and gx == 2160 and gy == 1624, ("custom, kept on the screen (200 px: 8 rows, 16 px): %d %d %d"):format(gx, gy, gw))
-- x as typed, the width cut to the rest of the screen (a full-width line moved right: x stayed 0 before)
gx, gy, gw = ns.Strip.Geometry("custom", 1700, 0, 2360)
assert(gx == 1700 and gy == 0 and gw == 660, ("x kept, width cut: %d %d %d"):format(gx, gy, gw))
-- a narrow line is a thicker one: the longest frame always fits
for _, width in ipairs({ 200, 220, 640, 1280, 2360 }) do
    local _, _, w, h = ns.Strip.Geometry("custom", 0, 0, width)
    local cells = math.floor(w / 2) * (h / 2)
    assert(ns.Protocol.MaxBytes(cells) >= ns.Strip.NEED_BYTES, ("width %d: %d bytes"):format(width, ns.Protocol.MaxBytes(cells)))
end
local _, _, _, thin = ns.Strip.Geometry("top")
local _, _, _, thick = ns.Strip.Geometry("custom", 0, 0, 220)
assert(thin == 2 and thick == 14, ("full width one row, 220 px seven: %d %d"):format(thin, thick))
ns.db.stripPlace, ns.db.stripX, ns.db.stripY, ns.db.stripWidth = "custom", 100, 50, 900
assert(ns.Strip.Describe() == "100,50,900,4,2360,1640", ns.Strip.Describe())
assert(ns.ControlPayload():find(";strip=100,50,900,4,2360,1640", 1, true), "the settings frame tells the place")
-- moving: the program is told first (ahead of the queue, where the strip is now), then it moves
ns.Strip.Initialize()
local firsts, pushed = {}, {}
ns.Strip.PushFirst = function(p) firsts[#firsts + 1] = p end
ns.Strip.Push = function(p) pushed[#pushed + 1] = p end
ns.Strip.MoveTo()
assert(#firsts == 1 and firsts[1]:find("^control\31") and firsts[1]:find("strip=100,50,900", 1, true), "told first")
assert(#pushed == 1 and pushed[1]:find("strip=100,50,900", 1, true), "and again from the new place")
assert(ns.db.stripGeometry == "100,50,900,4,2360,1640", "kept for a program started later")
ns.db.stripPlace = "bottom"
ns.StripWindow.Toggle()
local pending = ns.StripWindow.Pending()
assert(pending.place == "bottom" and pending.x == 0 and pending.y == 1638 and pending.width == 2360,
    ("the fields show the bottom line: %s %s %s"):format(pending.x, pending.y, pending.width))
ns.StripWindow.Pick("custom")
assert(pending.place == "custom" and pending.y == 1638 and pending.width == 2360, "a place of one's own starts from them")
ns.StripWindow.Pick("top")
assert(pending.y == 0, "top: its numbers")
-- a place of one's own, saved and opened again: as it was saved
ns.StripWindow.Pick("custom")
pending.x = 1700
ns.StripWindow.Save()
assert(ns.db.stripPlace == "custom" and ns.db.stripX == 1700 and ns.db.stripY == 0 and ns.db.stripWidth == 660,
    ("saved: %s %s %s %s"):format(ns.db.stripPlace, ns.db.stripX, ns.db.stripY, ns.db.stripWidth))
ns.StripWindow.Toggle()
pending = ns.StripWindow.Pending()
assert(pending.place == "custom" and pending.x == 1700 and pending.width == 660, "opened again: as saved")
ns.Strip.Preview("bottom")
ns.Strip.Preview(nil)
ns.db.stripPlace = "top"
print("strip place ok")
