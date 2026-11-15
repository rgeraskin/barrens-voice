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
        if k == "GetAlpha" then return function(self) return rawget(self, "_alpha") or 1 end end
        if k == "SetAlpha" then return function(self, v) self._alpha = v end end
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
PanelTemplates_SelectTab, PanelTemplates_DeselectTab, PanelTemplates_TabResize = function() end, function() end, function() end
UnitGUID = function() return "me" end
BackdropTemplateMixin = {}
C_Timer = { NewTimer = function(_, f) return { Cancel = function() end } end, NewTicker = function() end,
            After = function(_, f) f() end }
Settings = { RegisterCanvasLayoutCategory = function() return {} end, RegisterAddOnCategory = function() end }
local ns = {}
for _, f in ipairs({ "Protocol.lua", "Strip.lua", "Dictionary.lua", "VoiceList.lua", "Core.lua", "ChatFade.lua", "CompanionStatus.lua", "Companion.lua", "UI.lua",
                     "DictionaryWindow.lua", "StripWindow.lua", "Options.lua", "VoicesWindow.lua", "Minimap.lua" }) do
    assert(loadfile(f))("BarrensVoice", ns)
end
BarrensVoiceVoiceList = { { name = "Anna", label = "Anna (RHVoice)", gender = "Female", on = true },
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
ns.Options.Open("dictionary"); assert(ns.Options.Current() == "dictionary"); print("dictionary ok")
ns.Options.Open("voices"); assert(ns.Options.Current() == "voices"); print("voices ok")
ns.Options.Open("help"); assert(ns.Options.Current() == "help"); print("help tab ok")
assert(ns.Retail() == false, "no GetBuildInfo: Forever")
GetBuildInfo = function() return "12.1.5", "70783", "Nov 2026", 120105 end
assert(ns.Retail() == true, "retail by its interface version")
GetBuildInfo = function() return "1.60.1", "70938", "Nov 2026", 16001 end
assert(ns.Retail() == false, "Forever")
GetBuildInfo = nil
do  -- «Скачать дополнительные голоса …: RHVoice, Silero»: the companion is asked to open the page; the address goes to the chat too
    local pushedLink, saidLink, push0, print0 = {}, {}, ns.Strip.Push, print
    ns.Strip.Push = function(p) pushedLink[#pushedLink + 1] = p end
    print = function(t) saidLink[#saidLink + 1] = t end
    ns.OpenLink("silero")
    ns.OpenLink("https://evil.example")
    ns.CopyLink("discord")
    ns.Strip.Push, print = push0, print0
    assert(#pushedLink == 2 and pushedLink[1]:find("^open\31") and pushedLink[1]:find("\31silero$"), pushedLink[1] or "nothing")
    assert(pushedLink[2]:find("^copy\31") and pushedLink[2]:find("\31discord$"), pushedLink[2] or "nothing")
    assert(#saidLink == 2 and saidLink[1]:find("snakers4/silero-models", 1, true), "the address in the chat")
    assert(saidLink[2]:find("буфер обмена", 1, true), saidLink[2])
    print("links ok")
end
for _, name in ipairs({ "reading", "general", "no such tab" }) do ns.Options.Open(name) end
assert(ns.Options.Current() == "general", "an unknown tab: the first one")
print("tabs ok")
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
assert(#diag == 1 and diag[1]:find("озвучку квеста", 1, true), "the dropped one is reported to the program's log")
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
assert(sent[1] and sent[1]:find("^diag\31") and sent[1]:find("CatQuest играет: pack, 34 с — чат ждёт", 1, true), sent[1] or "nothing")
assert(#first == 2 and first[2]:find("^pause\31"), "CatQuest speaks: the program pauses, ahead of the queue")
ns.WatchCatQuest()
assert(#first == 2, "a pause is sent once")
ns.Send("party", "Вася-Степи", "Orc", 2, "WARRIOR", "", "в очередь")
assert(sent[2]:find("строка ждёт озвучку квеста", 1, true), sent[2] or "nothing")
CatQuestCore.state = { playing = false }
ns.WatchCatQuest()
ns.ReleaseHeld()
assert(sent[3]:find("озвучка квестов замолчала", 1, true) and sent[4]:find("в очередь", 1, true), tostring(sent[3]))
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
-- Wayfarer (WayfarerRU.Queue): the same wait, its radio stories too; not while the player paused it
clock = 400
sent = {}
WayfarerRU = { Queue = { paused = false, items = { { handle = 7, startedAt = 398, sound = { duration = 20 }, questID = 1 } } } }
ns.Send("party", "Вася-Степи", "Orc", 2, "WARRIOR", "", "во время квеста")
assert(#sent == 0, "held while Wayfarer reads a quest")
WayfarerRU.Queue.items[1] = { waiting = true, sound = { duration = 9 } }        -- after the NPC's greeting
ns.ReleaseHeld()
assert(#sent == 0, "held while Wayfarer is about to speak")
WayfarerRU.Queue.paused = true
ns.ReleaseHeld()
assert(#sent == 1 and sent[1]:find("во время квеста"), "Wayfarer paused by the player: the chat goes on")
WayfarerRU.Queue.paused = false
WayfarerRU.Queue.items[1] = { handle = 8, startedAt = 400, sound = { duration = 90 }, radio = "chronicles" }
ns.Send("party", "Вася-Степи", "Orc", 2, "WARRIOR", "", "под радио")
assert(#sent == 1, "held while its radio story plays")
WayfarerRU.Queue.items = {}
ns.ReleaseHeld()
assert(#sent == 2 and sent[2]:find("под радио"), "the radio over: the held line goes")
WayfarerRU.Queue.items[1] = { handle = 9, startedAt = 380, sound = { duration = 10 }, zone = "Элвиннский лес" }
ns.Send("party", "Вася-Степи", "Orc", 2, "WARRIOR", "", "после зависшего")
assert(#sent == 3, "a stuck Wayfarer item does not hold the chat")
first = {}
WayfarerRU.Queue.items[1] = { handle = 10, startedAt = 400, sound = { duration = 30 }, zone = "Элвиннский лес" }
ns.db.debug = true
ns.WatchCatQuest()
assert(#first == 1 and first[1]:find("^pause\31"), "Wayfarer speaks: the program pauses")
assert(sent[#sent]:find("Wayfarer играет: лор места, 30 с — чат ждёт", 1, true), sent[#sent])
WayfarerRU.Queue.items = {}
ns.WatchCatQuest()
assert(#first == 2 and first[2]:find("^resume\31"), "Wayfarer silent: the program goes on")
ns.db.debug = false
WayfarerRU = nil
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
assert(ns.IsQuestion("кто в ОП?") and ns.IsQuestion("танк нужен? хил?") and ns.IsQuestion("где? ") and ns.IsQuestion("что???"))
assert(not ns.IsQuestion("привет. кто идёт?") and not ns.IsQuestion("ура! кто со мной?") and not ns.IsQuestion("кто в ОП")
    and not ns.IsQuestion("ну... кто?") and not ns.IsQuestion("5.5 кто?"), "other sentences: no")
ns.Send("party", "Вася-Степи", "Orc", 2, "WARRIOR", "", "кто идёт в ОП?")
ns.Send("say", "Вася-Степи", "Orc", 2, "WARRIOR", "", "что тут?")
ns.Send("yell", "Вася-Степи", "Orc", 2, "WARRIOR", "", "что тут?")
ns.Send("party", "Вася-Степи", "Orc", 2, "WARRIOR", "", "привет, кто идёт?!")
assert(said(3) == "Вася спрашивает:\4 кто идёт в ОП?" and said(4) == "Вася спрашивает:\4 что тут?"
    and said(5) == "Вася кричит:\4 что тут?" and said(6) == "Вася пишет:\4 привет, кто идёт?!", said(3) .. " | " .. said(4) .. " | " .. said(5) .. " | " .. said(6))
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
ns.Options.Open("general"); ns.Options.Bridge(true)
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
ns.Options.Open("general"); ns.Options.Bridge(true)
pending = ns.StripWindow.Pending()
assert(pending.place == "custom" and pending.x == 1700 and pending.width == 660, "opened again: as saved")
ns.Strip.Preview("bottom")
ns.Strip.Preview(nil)
ns.db.stripPlace = "top"
print("strip place ok")

-- the chat windows out of sight: transparent without the mouse; a line not read aloud shows its window
local filters = {}
ChatTypeGroup = { SYSTEM = { "CHAT_MSG_SYSTEM" }, PARTY = { "CHAT_MSG_PARTY", "CHAT_MSG_PARTY_LEADER" } }
ChatFrame_AddMessageEventFilter = function(event, f) filters[event] = f end
hooksecurefunc = function(t, name, f)
    local orig = t[name]
    t[name] = function(...) if orig then orig(...) end f(...) end
end
wipe = function(t) for k in pairs(t) do t[k] = nil end return t end
ChatFrame1 = widget()
ChatFrame1._shown = true
ChatFrame1.isDocked, ChatFrame1.buttonFrame, ChatFrame1.ResizeButton = false, false, false
local editBox = widget()
editBox._focus = false
editBox.HasFocus = function(self) return self._focus end
editBox.IsVisible = function() return true end
editBox.IsMouseOver = function() return false end
ChatFrame1.editBox = editBox
CHAT_FRAMES = { "ChatFrame1" }
local now = 1000
GetTime = function() return now end
ns.db.enabled, ns.db.fadeChat, ns.db.party, ns.db.self = true, true, true, false
ns.ChatFade.Initialize()
local function settle(seconds) for _ = 1, 10 do ns.ChatFade.Update(nil, seconds / 10) end end
settle(2)
assert(ChatFrame1:GetAlpha() == 0, "no mouse: transparent " .. ChatFrame1:GetAlpha())
assert(editBox:GetAlpha() == 0, "the edit box too")
editBox._focus = true
settle(0.3)
assert(editBox:GetAlpha() == 1 and ChatFrame1:GetAlpha() == 1, "typing: the window and its edit box show")
editBox._focus = false
settle(2)
assert(editBox:GetAlpha() == 0, "done typing: out of sight again")
local function line(event, text, guid)
    filters[event](ChatFrame1, event, text, "Вася-Степи", "", "", "", "", 0, 0, "", 0, 1, guid)
    ChatFrame1:AddMessage(text)
end
line("CHAT_MSG_PARTY", "привет", "Player-1-2")
settle(0.3)
assert(ChatFrame1:GetAlpha() == 0, "a line read aloud: the window stays out of sight")
-- a General line: CHAT_MSG_CHANNEL is in no ChatTypeGroup list, yet it is read - no flash either
ns.db.channels = true
assert(filters.CHAT_MSG_CHANNEL, "the channels' messages have the filter too")
line("CHAT_MSG_CHANNEL", "кто в ОП?", "Player-1-3")
settle(0.3)
assert(ChatFrame1:GetAlpha() == 0, "a General line read aloud: the window stays out of sight")
line("CHAT_MSG_SYSTEM", "Вы получили 5 серебра")
settle(0.3)
assert(ChatFrame1:GetAlpha() == 1, "a system line is not read: the window shows")
now = now + 11
settle(2)
assert(ChatFrame1:GetAlpha() == 0, "10 s later: out of sight again")
line("CHAT_MSG_PARTY", "моя строка", "me")
settle(0.3)
assert(ChatFrame1:GetAlpha() == 1, "one's own line, not read: shows")
now = now + 11
settle(2)
ChatFrame1:AddMessage("|cff40c0ffДругой аддон:|r что-то")
settle(0.3)
assert(ChatFrame1:GetAlpha() == 1, "an addon's print (no chat event): shows")
ns.askingFilters = true
assert(filters.CHAT_MSG_PARTY(ChatFrame1, "CHAT_MSG_PARTY", "x") == false, "the filter never hides a line")
ns.askingFilters = false
-- the mouse over the chat counts only when nothing else lies over it there
now = now + 20
settle(2)
ChatFrame1.IsMouseOver = function() return true end
ChatFrame1.GetName = function() return "ChatFrame1" end
local map = widget()
map.GetName = function() return "WorldMapFrame" end
map.GetParent = function() return nil end
GetMouseFocus = function() return map end
settle(0.5)
assert(ChatFrame1:GetAlpha() == 0, "a map over the chat: the mouse there does not count")
GetMouseFocus = function() return ChatFrame1 end
settle(0.3)
assert(ChatFrame1:GetAlpha() == 1, "the mouse on the chat itself: shows")
GetMouseFocus = function() return WorldFrame end
assert(ns.ChatFade.MouseOnChat(), "nothing under the mouse (the world): free")
local tab = widget()
tab.GetName = function() return "ChatFrame1Tab" end
GetMouseFocus = function() return tab end
assert(ns.ChatFade.MouseOnChat(), "its tab: the chat's")
GetMouseFocus = nil
ChatFrame1.IsMouseOver = function() return false end
now = now + 20
settle(2)
-- whispers and guild lines show the window if asked, though they are read aloud
ns.db.whisper, ns.db.guild = true, true
now = now + 20
settle(2)
line("CHAT_MSG_WHISPER", "привет", "Player-1-4")
settle(0.3)
assert(ChatFrame1:GetAlpha() == 0, "a read whisper: no flash, as before")
ns.db.fadeWhisper = true
line("CHAT_MSG_WHISPER", "привет", "Player-1-4")
settle(0.3)
assert(ChatFrame1:GetAlpha() == 1, "a whisper with the option on: the window shows")
now = now + 20
settle(2)
ns.db.fadeGuild = true
line("CHAT_MSG_GUILD", "всем привет", "Player-1-5")
settle(0.3)
assert(ChatFrame1:GetAlpha() == 1, "a guild line with the option on: the window shows")
now = now + 20
settle(2)
ns.db.fadeWhisper, ns.db.fadeGuild = false, false
line("CHAT_MSG_GUILD", "ещё раз", "Player-1-5")
settle(0.3)
assert(ChatFrame1:GetAlpha() == 0, "options off again: a guild line does not show it")
-- a line in a tab that is not the one shown, and the combat log: no flash
local log = widget()
log._shown, log.isDocked, log.buttonFrame, log.editBox, log.ResizeButton = false, true, false, false, false
ChatFrame2 = log
CHAT_FRAMES = { "ChatFrame1", "ChatFrame2" }
GENERAL_CHAT_DOCK = widget()
GENERAL_CHAT_DOCK.IsMouseOver = function() return false end
GENERAL_CHAT_DOCK.overflowButton = false
ChatFrame1.isDocked = true
FCFDock_GetSelectedWindow = function() return ChatFrame1 end
settle(2)                                     -- hooks the new window; the new tab strip fades
filters.CHAT_MSG_SYSTEM(ChatFrame2, "CHAT_MSG_SYSTEM", "Hobby Warrior создает: Медный слиток.")
ChatFrame2:AddMessage("Hobby Warrior создает: Медный слиток.")
settle(0.5)
assert(ChatFrame1:GetAlpha() == 0 and GENERAL_CHAT_DOCK:GetAlpha() == 0, "a background tab's line: no flash")
-- switched to that tab: its lines show the chat like any other
FCFDock_GetSelectedWindow = function() return ChatFrame2 end
ChatFrame2._shown = true
ChatFrame2:AddMessage("Вы наносите 12 ед. урона")
settle(0.5)
assert(GENERAL_CHAT_DOCK:GetAlpha() == 1, "the tab on screen: its line shows the chat")
now = now + 20
ChatFrame2._shown = false
FCFDock_GetSelectedWindow, GENERAL_CHAT_DOCK, ChatFrame2 = nil, nil, nil
CHAT_FRAMES = { "ChatFrame1" }
ChatFrame1.isDocked = false
ns.db.fadeChat = false
ns.ChatFade.Apply()
assert(ChatFrame1:GetAlpha() == 1, "the setting off: the chat as it was")
assert(editBox:GetAlpha() == 1, "and its edit box")
print("chat fade ok")

-- is the companion running: the time it writes into CompanionStatus.lua, read when the addon loads
local said, realPrint = {}, print
print = function(text) said[#said + 1] = text end
local Co = ns.Companion
Co.Read({ beat = 1000 }, 1010)
assert(Co.State() == "running", "a fresh time: running")
Co.SayAtLogin()
assert(said[1]:find("озвучка чата работает"), tostring(said[1]))
Co.Read({ beat = 1000 }, 1100)
assert(Co.State() == "stopped", "a time over 45 s old: not running")
Co.Read(nil, 1100)
assert(Co.State() == "stopped", "no time at all (the file as shipped): not running")
Co.SayAtLogin()
assert(said[2]:find("приложение%-компаньон Barrens Voice не запущено — чат будет озвучиваться, как только"), tostring(said[2]))
assert(Co.Describe():find("не был запущен"), Co.Describe())
Co.Read({ beat = 1000 }, 1010)
assert(Co.Describe():find("был запущен") and not Co.Describe():find("не был"), Co.Describe())
Co.Read(nil, 1100)
-- not running at login: the transparent chat is hidden all the same (a companion started later reads it)
ns.db.fadeChat = true
ChatFrame1:SetAlpha(1)
now = now + 20                               -- past the 10 s the last line not read showed the window for
for _ = 1, 10 do ns.ChatFade.Update(nil, 0.3) end
assert(ChatFrame1:GetAlpha() == 0, "the setting decides, not a state that may be old")
ns.db.fadeChat = false
ns.ChatFade.Apply()
Co.Read({ beat = 1000 }, 1010)
print = realPrint
print("companion ok")

-- the word at login: the welcome on the first run, a line after an update, then the companion's line
local welcome, plainPrint = {}, print
print = function(text) welcome[#welcome + 1] = text end
GetAddOnMetadata = function() return "0.3.0" end
ns.firstRun, ns.db.seenVersion = true, nil
ns.LoginWord()
assert(#welcome == 5 and welcome[1]:find("добро пожаловать") and welcome[2]:find("приложение%-компаньон")
    and welcome[4]:find("«Помощь»", 1, true) and welcome[5]:find("озвучка чата"), "welcome, then whether the reading works")
assert(ns.db.seenVersion == "0.3.0", "the version is kept")
ns.firstRun = false
welcome = {}
ns.LoginWord()
assert(#welcome == 1 and welcome[1]:find("озвучка чата"), "the same version again: only whether the reading works")
welcome = {}
ns.db.seenVersion = "0.2.1"                  -- an update
ns.LoginWord()
assert(#welcome == 3 and welcome[1]:find("обновление 0.3.0: ритейл WoW") and welcome[2]:find("«Помощь»", 1, true),
    tostring(welcome[1]))
ns.db.seenVersion = nil                      -- from a version before the line was there: the line too
welcome = {}
ns.LoginWord()
assert(#welcome == 3 and welcome[1]:find("обновление 0.3.0"), "an update from before 0.2.1")
GetAddOnMetadata = function() return "9.9.9" end
ns.db.seenVersion = "0.2.1"
welcome = {}
ns.LoginWord()
assert(welcome[1]:find("что нового — в описании аддона"), "a version with no news of its own")
GetAddOnMetadata = nil
print = plainPrint
print("welcome ok")

-- /bv last: the lines again, in order, marked replay=1; a sender with no race known keeps its line
local replayed = {}
ns.Strip.Push = function(p) replayed[#replayed + 1] = p end
ns.db.enabled, ns.db.waitForCatQuest = true, false
ns.history = {}
local function remember(...) table.insert(ns.history, { n = select("#", ...), ... }) end
remember("party", "Вася-Степи", "Orc", 2, "WARRIOR", "", "первая")
remember("party", "Петя-Степи", nil, nil, nil, "", "вторая")       -- race not known yet
remember("party", "Вася-Степи", "Orc", 2, "WARRIOR", "", "третья")
local plainPrint2 = print
print = function() end
ns.Replay(3)
print = plainPrint2
assert(#replayed == 3, "all three: " .. #replayed)
for k, word in ipairs({ "первая", "вторая", "третья" }) do
    assert(replayed[k]:find(word, 1, true) and replayed[k]:find("replay=1", 1, true), "in order, marked: " .. k)
end
ns.Send("party", "Вася-Степи", "Orc", 2, "WARRIOR", "", "живая")
assert(not replayed[4]:find("replay=1", 1, true), "a live line after it: not marked")
print("replay ok")

-- lines other players' addons write: not read (Questie, DBM...), a player's own words are
local AL = ns.AddonLine
assert(AL("{звезда} Questie: Сердце Тарагамана Ненасытного: 1/1 для |cffffff00|Hquest:5761:0|h[Убить тварь]|h|r!") == "Questie")
assert(AL("{rt1} Interrupted: Fireball") == "Interrupted", "an icon and a Latin word with a colon")
assert(AL("<DBM> Pull in 5") == "DBM" and AL("[Questie] accepted") == "Questie" and AL("Details!: Damage Done") == "Details!")
assert(AL("Полуказуальная RU/UA гильдия <MIR> ищет игроков!") == nil, "a guild tag inside a player's line")
assert(AL("[UA] Спільнота < ХАОС > запрошує") == nil, "[UA] is no addon")
assert(AL("{череп} танк: бери этого") == nil, "an icon, then Russian: a player")
assert(AL("WTS: сумки") == nil and AL("Nova: привет") == nil, "a Latin word with a colon that is no addon")
ns.db.enabled, ns.db.party, ns.db.self = true, true, false
assert(not ns.Reads("CHAT_MSG_PARTY", "Player-1-9", "{звезда} Questie: Баззалан – убито: 1/1"), "not read")
assert(ns.Reads("CHAT_MSG_PARTY", "Player-1-9", "кто идёт в ОП?"), "a player's line: read")
ns.db.skipAddons = false
assert(ns.Reads("CHAT_MSG_PARTY", "Player-1-9", "{звезда} Questie: Баззалан – убито: 1/1"), "the setting off: read")
ns.db.skipAddons = true
print("addon lines ok")

-- the history outlives a /reload: it is the saved variables' table
local kept = {}
ns.Strip.Push = function(p) kept[#kept + 1] = p end
ns.db.history = { { n = 7, "party", "Вася-Степи", "Orc", 2, "WARRIOR", "", "до перезагрузки" },
                  { n = 7, [1] = "party", [2] = "Петя-Степи", [6] = "", [7] = "без расы" } }   -- as saved, a hole kept out
ns.RestoreHistory()
assert(ns.history == ns.db.history, "the same table: what is added is saved")
local quiet = print
print = function() end
ns.Replay(2)
print = quiet
assert(#kept == 2 and kept[1]:find("до перезагрузки", 1, true) and kept[2]:find("без расы", 1, true), "replayed after a reload")
ns.db.history = "broken"
ns.RestoreHistory()
assert(type(ns.history) == "table" and #ns.history == 0, "a broken saved value: a fresh history")
print("history ok")

-- numbered channels one by one (under "Общие каналы")
local CS = ns.ChannelSetting
assert(CS("Общий", "1. Общий - Оргриммар") == "chGeneral" and CS("General") == "chGeneral")
assert(CS("Торговля (локальный)", "") == "chTrade" and CS("Trade - City") == "chTrade")
assert(CS("Поиск спутников") == "chLfg" and CS("LookingForGroup") == "chLfg")
assert(CS("Оборона: Оргриммар") == "chDefense" and CS("LocalDefense") == "chDefense" and CS("Оборона мира") == "chDefense")
assert(CS("МойКанал") == "chOther" and CS(nil, "5. Мой") == "chOther" and CS(nil, "2. Торговля - Степи") == "chTrade", "by the full channel name when no base name")
ns.db.enabled, ns.db.channels, ns.db.self = true, true, false
ns.db.chGeneral, ns.db.chTrade, ns.db.chLfg, ns.db.chDefense, ns.db.chOther = true, false, true, true, true
assert(ns.Reads("CHAT_MSG_CHANNEL", "Player-1-9", "кто в ОП?", "Общий", "1. Общий - Степи"), "General on")
assert(not ns.Reads("CHAT_MSG_CHANNEL", "Player-1-9", "продам сумки", "Торговля (локальный)", "2. Торговля"), "Trade off")
ns.db.channels = false
assert(not ns.Reads("CHAT_MSG_CHANNEL", "Player-1-9", "кто в ОП?", "Общий", "1. Общий"), "channels off: none")
ns.db.channels, ns.db.chTrade = true, true
print("numbered channels ok")

-- the sliders' 100 % stands for the program's 125 % speed and 120 % volume
ns.db.rate, ns.db.volume, ns.db.voices = 100, 100, "f5"
assert(ns.LineOptions():find("rate=125;vol=120;", 1, true), ns.LineOptions())
ns.db.rate, ns.db.volume = 160, 200
assert(ns.LineOptions():find("rate=200;vol=240;", 1, true), "the top of the sliders is within the program's limits: " .. ns.LineOptions())
ns.db.rate, ns.db.volume = 40, 0
assert(ns.LineOptions():find("rate=50;vol=0;", 1, true), ns.LineOptions())
local old = { rate = 125, volume = 120 }              -- saved before: the same sound is 100 and 100 now
ns.MigrateScale(old)
assert(old.rate == 100 and old.volume == 100 and old.scale == 1, old.rate .. " " .. old.volume)
old = { rate = 200, volume = 200 }                    -- the program's top: the sliders' top
ns.MigrateScale(old)
assert(old.rate == 160 and old.volume == 165, old.rate .. " " .. old.volume)
old = { rate = 100, volume = 100 }
ns.MigrateScale(old)
assert(old.rate == 80 and old.volume == 85, "100 of the program's own scale: " .. old.rate .. " " .. old.volume)
ns.MigrateScale(old)
assert(old.rate == 80, "migrated once")
ns.db.rate, ns.db.volume = 100, 100
print("scale ok")

-- channel labels carry the client's own slash commands, the fallback where the client has none
SLASH_PARTY1, SLASH_PARTY2, SLASH_PARTY3 = "/гр", "/группа", "/p"
SLASH_RAID1, SLASH_RAID2, SLASH_RAID3 = "/рейд", "/raid", "/р"
SLASH_GUILD1, SLASH_GUILD2 = "/g", "/gu"
local CL = ns.Options.ChannelLabel
assert(CL({ "party", "Группа", "PARTY", "/p" }) == "Группа (/гр)", "the shortest in the client's own letters")
assert(CL({ "raid", "Рейд", "RAID", "/ra" }) == "Рейд (/р)", CL({ "raid", "Рейд", "RAID", "/ra" }))
assert(CL({ "guild", "Гильдия", "GUILD", "/g" }) == "Гильдия (/g)", "Latin only: the shortest")
assert(CL({ "officer", "Офицеры", "OFFICER", "/o" }) == "Офицеры (/o)", "none: the fallback")
assert(CL({ "self", "Свои сообщения" }) == "Свои сообщения", "no command")
SLASH_PARTY1, SLASH_PARTY2, SLASH_PARTY3, SLASH_RAID1, SLASH_RAID2, SLASH_RAID3, SLASH_GUILD1, SLASH_GUILD2 = nil
print("channel labels ok")

-- retail's closed chat: secret text, sender and GUID are not touched or read; the window shows the line
local SECRET = setmetatable({}, { __tostring = function() error("a secret value cannot be read") end,
    __index = function() error("a secret value cannot be read") end,
    __concat = function() error("a secret value cannot be read") end,
    __eq = function() error("a secret value cannot be compared") end })
issecretvalue = function(v) return rawequal(v, SECRET) end
assert(ns.Secret("обычный", "Вася") == false and ns.Secret("обычный", SECRET) == true)
local pushed, told, quiet2 = {}, {}, print
ns.Strip.Push = function(p) pushed[#pushed + 1] = p end
print = function(t) told[#told + 1] = t end
ns.db.enabled, ns.db.party, ns.db.onlyVisible = true, true, false
local function event(text, sender, guid)
    ns.OnEvent("CHAT_MSG_PARTY", text, sender, "", "", "", "", 0, 0, "", 0, 1, guid)
end
event(SECRET, SECRET, SECRET)
event(SECRET, SECRET, SECRET)
assert(#pushed == 0, "a secret line is not sent")
assert(#told == 1 and told[1]:find("закрывает чат от аддонов"), "told once while it lasts: " .. #told)
event("кто идёт?", "Вася-Степи", "Player-1-2")
assert(#pushed == 1, "an open line after it is sent")
event(SECRET, SECRET, SECRET)
assert(#told == 2, "closed again later: told again")
-- the chat window: a secret line shows it (the filter does not read it)
ns.db.fadeChat = true
ChatFrame1:SetAlpha(1)
now = now + 30
for _ = 1, 10 do ns.ChatFade.Update(nil, 0.3) end
assert(ChatFrame1:GetAlpha() == 0, "hidden before")
ns.db.debug = true
filters.CHAT_MSG_PARTY(ChatFrame1, "CHAT_MSG_PARTY", SECRET, SECRET, "", "", "", "", 0, 0, "", 0, 1, SECRET)
ChatFrame1:AddMessage(SECRET)
for _ = 1, 2 do ns.ChatFade.Update(nil, 0.3) end
assert(ChatFrame1:GetAlpha() == 1, "a closed-chat line shows the window")
ns.db.debug, ns.db.fadeChat = false, false
ns.ChatFade.Apply()
print = quiet2
issecretvalue = nil
print("secret chat ok")
