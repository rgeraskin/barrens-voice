-- Minimal WoW API stubs: run the addon's files and open every window, to catch nil calls and typos.
local created = {}    -- what widgets made (textures, font strings)
local function widget()
    local w = { _text = "", _shown = false, _checked = false, _scripts = {} }
    return setmetatable(w, { __index = function(t, k)
        if k == "GetText" then return function(self) return self._text end end
        if k == "SetText" then return function(self, v) self._text = v or "" end end
        if k == "GetHeight" or k == "GetWidth" or k == "GetStringWidth" then return function() return 100 end end
        if k == "GetStringHeight" then return function(self)
            local _, breaks = tostring(self._text):gsub("\n", "")
            return 14 * (breaks + 1)
        end end
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
        if k == "SetTexture" then return function(self, v) self._texture = v end end
        if k == "SetTexCoord" then return function(self, ...) self._coords = { ... } end end
        if k == "SetSize" then return function(self, w, h) self._w, self._h = w, h end end
        if k:match("^Create") then return function() local made = widget(); created[#created + 1] = made; return made end end
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
-- The chat filters as the Forever client keeps them (Blizzard_ChatFrameBase/Shared/ChatFrameFilters.lua):
-- per event, in the order added, each called (frame, event, ...) - an error counts as no answer; the first
-- result true discards the line, a second result replaces the arguments for the filters after it.
-- ProcessMessageEventFilters returns (discard, arguments...). There is no ChatFrame_GetMessageEventFilters.
local chatFilters = {}
ChatFrameUtil = {
    AddMessageEventFilter = function(event, f)
        chatFilters[event] = chatFilters[event] or {}
        for _, g in ipairs(chatFilters[event]) do if g == f then return end end
        table.insert(chatFilters[event], f)
    end,
    RemoveMessageEventFilter = function(event, f)
        for i, g in ipairs(chatFilters[event] or {}) do if g == f then table.remove(chatFilters[event], i) return end end
    end,
    ProcessMessageEventFilters = function(frame, event, ...)
        local function pack(...) return { n = select("#", ...), ... } end
        local args = pack(...)
        for _, f in ipairs(chatFilters[event] or {}) do
            local r = pack(pcall(f, frame, event, unpack(args, 1, args.n)))
            if r[1] then
                if r[2] then return true, unpack(args, 1, args.n) end
                if r[3] then args = pack(unpack(r, 3, r.n)) end
            end
        end
        return false, unpack(args, 1, args.n)
    end,
}
local ns = {}
dofile("../../companion/tests/toc.lua")(ns)   -- every file, in the .toc's order
BarrensVoiceVoiceList = { { name = "Anna", label = "Anna (RHVoice)", gender = "Female", on = true },
                          { name = "Aidar (Russian)", label = "Aidar (Silero)", gender = "Male", on = true } }
ns.db = setmetatable({ rate = 100, voices = "f5", enabled = true,
                       sayNames = true, sayVerb = true, minimapIcon = true }, {})
ns.Dictionary.Migrate(ns.db)
ns.Dictionary.Rebuild()
local sent = {}
ns.Strip.Push = function(p) sent[#sent + 1] = p end
-- every check box and radio button of the settings, where it is and its label: none may run into another or off the window
local boxes, check0 = {}, ns.UI.Check
ns.UI.Check = function(parent, x, y, label, ...)
    local c = check0(parent, x, y, label, ...)
    boxes[#boxes + 1] = { parent = parent, x = x, y = y, label = label, box = c }
    return c
end
local radio0 = ns.UI.Radio
ns.UI.Radio = function(parent, x, y, label, ...)
    local r = radio0(parent, x, y, label, ...)
    boxes[#boxes + 1] = { parent = parent, x = x - 4, y = y, label = label, box = r }   -- 18 px and 4: as a check box's 26 less 4
    return r
end
ns.Options.Initialize()
ns.db.volume = 150
ns.Options.Toggle(); assert(ns.db.volume == 150 and ns.db.rate == 100, "Refresh must keep the settings")
print("options ok")
do  -- a check box and its label: 26 px, then about 7 px a letter (GameFontHighlight); the window is 580 wide
    local function right(b) return b.x + 26 + 7 * select(2, b.label:gsub("[^\128-\191]", "")) end
    for i, a in ipairs(boxes) do
        assert(right(a) <= 580 - 8, ("«%s» runs off the window: %d"):format(a.label, right(a)))
        for j = i + 1, #boxes do
            local b = boxes[j]
            if a.parent == b.parent and math.abs(a.y - b.y) < 20 and a.x < right(b) and b.x < right(a) then
                error(("«%s» and «%s» run into each other"):format(a.label, b.label))
            end
        end
    end
    assert(#boxes > 20, "the settings' check boxes seen: " .. #boxes)
    print("check boxes apart ok")
end
ns.Options.Open("dictionary"); assert(ns.Options.Current() == "dictionary"); print("dictionary ok")
ns.Options.Open("voices"); assert(ns.Options.Current() == "voices"); print("voices ok")
ns.Options.Open("help"); assert(ns.Options.Current() == "help"); print("help tab ok")
do  -- the community's icon: the Blizzard logo as the chat shows it, its 24x16 part, not squashed
    local logo
    for _, w in ipairs(created) do
        if rawget(w, "_texture") == "Interface\\ChatFrame\\UI-ChatIcon-Blizz" then logo = w end
    end
    assert(logo, "the community's row has the Blizzard logo")
    local c = logo._coords
    assert(c and c[1] == 4 / 32 and c[2] == 28 / 32 and c[3] == 0 and c[4] == 1, "its texcoords")
    assert(logo._w / logo._h == 24 / 16, "its own proportions")
    print("community icon ok")
end
assert(ns.Retail() == false, "no GetBuildInfo: Forever")
GetBuildInfo = function() return "12.1.5", "70783", "Nov 2026", 120105 end
assert(ns.Retail() == true, "retail by its interface version")
GetBuildInfo = function() return "1.60.1", "70938", "Nov 2026", 16001 end
assert(ns.Retail() == false, "Forever")
GetBuildInfo = nil
do  -- CatQuest and Wayfarer are Forever's addons: on retail /bv debug names neither, and no one watches them
    local told, tickers, print0, ticker0, debug0 = {}, {}, print, C_Timer.NewTicker, ns.db.debug
    print = function(t) told[#told + 1] = t end
    C_Timer.NewTicker = function(seconds, f) tickers[#tickers + 1] = f end
    local function debugWord(interface)
        GetBuildInfo = function() return "", "", "", interface end
        ns.db.debug = false
        SlashCmdList.BARRENSVOICE("debug")
        return told[#told]
    end
    local function watched(interface)
        GetBuildInfo = function() return "", "", "", interface end
        tickers = {}
        local word, control, dictionary = ns.LoginWord, ns.SendControl, ns.SendDictionary   -- only the tickers here
        ns.LoginWord, ns.SendControl, ns.SendDictionary = function() end, function() end, function() end
        ns.OnEvent("PLAYER_LOGIN")
        ns.LoginWord, ns.SendControl, ns.SendDictionary = word, control, dictionary
        for _, f in ipairs(tickers) do if f == ns.WatchCatQuest then return true end end
        return false
    end
    assert(debugWord(16001):find("CatQuest", 1, true), "Forever: CatQuest's speech is in the debug log")
    assert(not debugWord(120105):find("CatQuest", 1, true), "retail: no word of it")
    assert(watched(16001) and not watched(120105), "the quest voice-overs watched on Forever only")
    GetBuildInfo, print, C_Timer.NewTicker, ns.db.debug = nil, print0, ticker0, debug0
    print("Forever's addons not on retail ok")
end
do  -- the channels' tooltips: Battle.net whispers are read too; retail's closed group chat is said on retail only
    local function tooltips(retail)
        local all = {}
        for _, item in ipairs(ns.Options.CHANNELS) do all[#all + 1] = ns.Options.ChannelTip(item, retail) end
        return table.concat(all, "\n")
    end
    local forever, retail = tooltips(false), tooltips(true)
    for _, all in ipairs({ forever, retail }) do
        assert(all:find("от друзей Battle.net", 1, true) and not all:find("Battle.net не", 1, true),
            "whispers: Battle.net's are read too")
    end
    assert(not forever:find("В ритейле", 1, true), "Forever: no word of retail")
    local _, closed = retail:gsub("игра закрывает этот чат от аддонов", "")
    assert(closed == 3, "retail: party, raid and raid warnings say where they are closed: " .. closed)
    assert(retail:find("В ритейле он почти не озвучивается", 1, true), "retail: the instance chat")
    print("channel tooltips ok")
end
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
do  -- «Открыть» for the community: its invite as a link in the chat, for the player to click (the click is the game's)
    local pushed, told, push0, print0 = {}, {}, ns.Strip.Push, print
    ns.Strip.Push = function(p) pushed[#pushed + 1] = p end
    print = function(t) told[#told + 1] = t end
    local enabled = true
    C_Club = { IsEnabled = function() return enabled end }
    Enum = { ClubType = { BattleNet = 0 } }
    GetClubTicketLink = function(ticket, name, clubType)
        assert(clubType == 0, "a Battle.net community")
        return "|cff82c5ff|HclubTicket:" .. ticket .. "|h[" .. name .. "]|h|r"
    end
    CommunitiesHyperlink = { OnClickLink = function() error("the addon must not open it itself (taint)") end }
    ns.OpenLink("community")
    assert(#pushed == 0, "the companion is not asked")
    assert(#told == 1 and told[1]:find("|HclubTicket:N9KR2WNHDgW|h[Barrens Voice]|h", 1, true), told[1] or "nothing said")
    assert(told[1]:find("щёлкните по ссылке", 1, true), "the player is told to click it: " .. told[1])
    ns.db.enabled = false                                    -- no companion needed: with the voice-over off too
    ns.OpenLink("community")
    ns.db.enabled = true
    assert(#told == 2 and #pushed == 0, "off: the link all the same")
    GetClubTicketLink = function() error("no CLUB_INVITE_HYPERLINK_TEXT") end      -- the client's helper fails
    LinkUtil, LinkTypes = { FormatLink = function(kind, text, ...)
        return ("|H%s:%s|h%s|h"):format(kind, table.concat({ ... }, ":"), text)
    end }, { ClubTicket = "clubTicket" }
    ns.OpenLink("community")
    assert(told[3]:find("|HclubTicket:N9KR2WNHDgW|h[Barrens Voice]|h", 1, true), "LinkUtil.FormatLink's link: " .. told[3])
    enabled = false                                          -- communities off: the browser, through the companion
    ns.OpenLink("community")
    assert(#pushed == 1 and pushed[1]:find("^open\31") and pushed[1]:find("\31community$"), pushed[1] or "nothing")
    C_Club = nil
    ns.OpenLink("community")
    assert(#pushed == 2, "no communities at all: the browser")
    ns.OpenLink("discord")
    assert(#pushed == 3 and pushed[3]:find("\31discord$"), "other links: the browser as before")
    ns.CopyLink("community")
    assert(#pushed == 4 and pushed[4]:find("^copy\31") and pushed[4]:find("\31community$"), "«Копировать»: the web address")
    C_Club, Enum, GetClubTicketLink, CommunitiesHyperlink, LinkUtil, LinkTypes = nil
    ns.Strip.Push, print = push0, print0
    print("community link ok")
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
do  -- the realm: never said (the client's "short"; "none" keeps another realm's, as the chat shows it), kept in the payload
    local asked
    Ambiguate = function(name, context)
        asked = context
        return context == "short" and name:match("^[^-]+") or name
    end
    local n = #sent
    ns.Send("party", "Вася-Степи", "Orc", 2, "WARRIOR", "", "с другого сервера")
    local fields = {}
    for f in (sent[n + 1] .. "\31"):gmatch("(.-)\31") do fields[#fields + 1] = f end
    assert(asked == "short", tostring(asked))
    assert(fields[2] == "Вася-Степи", "the payload keeps the whole sender: " .. fields[2])
    assert(fields[8]:find("^Вася[:,]") and not fields[8]:find("Степи"), "the spoken name has no realm: " .. fields[8])
    Ambiguate = nil
    print("realm not said ok")
end

-- Only what the chat windows show: window 1 is open (say, party, the zone channel "Общий"),
-- window 2 (guild) is closed, and a chat filter hides lines with "спам".
NUM_CHAT_WINDOWS = 2
ChatFrame1 = { messageTypeList = { "SAY", "PARTY" }, channelList = { "Общий" }, zoneChannelList = { 1 } }
ChatFrame2 = { messageTypeList = { "GUILD" }, channelList = {}, zoneChannelList = {} }
GetChatWindowInfo = function(i)
    if i == 1 then return "Общий", 14, 1, 1, 1, 1, true, false, 1 end
    return "Гильдия", 14, 1, 1, 1, 1, false, false, nil
end
local function spamFilter(_, _, msg) return msg:find("спам") ~= nil end
ChatFrameUtil.AddMessageEventFilter("CHAT_MSG_SAY", function() error("a broken filter of another addon") end)
ChatFrameUtil.AddMessageEventFilter("CHAT_MSG_SAY", spamFilter)
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
-- a client with the old global list only (no ChatFrameUtil), and one with neither
local util = ChatFrameUtil
ChatFrameUtil = nil
ChatFrame_GetMessageEventFilters = function(event) return event == "CHAT_MSG_SAY" and { spamFilter } or nil end
assert(not fire("CHAT_MSG_SAY", "это спам") and fire("CHAT_MSG_SAY", "привет"), "the old clients' filter list")
ChatFrame_GetMessageEventFilters = nil
assert(fire("CHAT_MSG_SAY", "это спам"), "no filter API at all: shown")
ChatFrameUtil = util
-- only the selected tab (onlyActiveTab): window 2 (guild) docked as a second tab, window 3 (yells) a
-- separate window; window 1 selected
do
    NUM_CHAT_WINDOWS = 3
    ChatFrame3 = { messageTypeList = { "YELL" }, channelList = {}, zoneChannelList = {} }
    local info = GetChatWindowInfo
    GetChatWindowInfo = function(i)
        if i == 1 then return "Общий", 14, 1, 1, 1, 1, true, false, 1 end
        if i == 2 then return "Гильдия", 14, 1, 1, 1, 1, true, false, 2 end
        return "Крики", 14, 1, 1, 1, 1, true, false, nil
    end
    GENERAL_CHAT_DOCK = {}
    local selected = ChatFrame1
    FCFDock_GetSelectedWindow = function(dock) assert(dock == GENERAL_CHAT_DOCK) return selected end
    assert(fire("CHAT_MSG_GUILD", "гильдия"), "off: any tab counts, a hidden one too")
    ns.db.onlyActiveTab = true
    assert(fire("CHAT_MSG_SAY", "привет"), "the selected tab's line")
    assert(not fire("CHAT_MSG_GUILD", "гильдия"), "another tab's line: not read")
    ns.db.debug = true
    fire("CHAT_MSG_GUILD", "гильдия")
    assert(sent[1]:find("^diag\31") and sent[1]:find("не в выбранной вкладке чата", 1, true), sent[1])
    ns.db.debug = false
    assert(fire("CHAT_MSG_YELL", "кричу"), "a separate window counts whatever tab is selected")
    selected = ChatFrame2
    assert(fire("CHAT_MSG_GUILD", "гильдия") and not fire("CHAT_MSG_SAY", "привет"), "the guild tab selected")
    FCFDock_GetSelectedWindow = nil
    assert(fire("CHAT_MSG_SAY", "привет"), "no dock on this client: every tab counts")
    ns.db.onlyVisible = false
    selected = ChatFrame2
    FCFDock_GetSelectedWindow = function() return selected end
    assert(fire("CHAT_MSG_SAY", "привет"), "only visible off: the tab does not matter either")
    ns.db.onlyVisible, ns.db.onlyActiveTab = true, false
    NUM_CHAT_WINDOWS, ChatFrame3, GetChatWindowInfo, GENERAL_CHAT_DOCK, FCFDock_GetSelectedWindow = 2, nil, info, nil, nil
end
ns.db.onlyVisible = false
assert(fire("CHAT_MSG_YELL", "кричу"), "everything when the option is off")
ChatFrameUtil.RemoveMessageEventFilter("CHAT_MSG_SAY", spamFilter)
print("visible ok")

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
-- «Озвучить» right after an edit: the edit goes before the line (not 2 s later, after it)
UnitName, UnitClass, UnitRace, UnitSex = function() return "Громмаш" end, function() return "Воин", "WARRIOR" end,
    function() return "Орк", "Orc" end, function() return 2 end
local tryBox
for _, f in ipairs(frames) do
    if f._scripts.OnEnterPressed and f._text == "WTS сумки, нужен дд в ОП" then tryBox = f end
end
assert(tryBox, "the line to try")
ns.Dictionary.SetText(ns.Dictionary.Text() .. "зюзябра=проверка\n")
sent = {}
tryBox._scripts.OnEnterPressed(tryBox)
assert(#sent >= 2 and sent[1]:find("^dict\31") and sent[1]:find("зюзябра=проверка", 1, true), sent[1] or "nothing")
assert(sent[#sent]:find("^test\31"), "then the line")
sent = {}
tryBox._scripts.OnEnterPressed(tryBox)
assert(#sent == 1 and sent[1]:find("^test\31"), "the layer unchanged since: not sent again")
ns.Dictionary.Reset()
UnitName, UnitClass, UnitRace, UnitSex = nil, nil, nil, nil
print("try a line ok")
-- the layer in parts: each at most 480 bytes, cut at line ends, "id=..;part=i;of=n"; joined, the layer
local function parts()
    local out, id = {}, nil
    for i, p in ipairs(sent) do
        local f = {}
        for x in (p .. "\31"):gmatch("(.-)\31") do f[#f + 1] = x end
        assert(f[1] == "dict" and #f == 8, p)
        local pid, part, of = f[7]:match("^id=(%x+);part=(%d+);of=(%d+)$")
        assert(pid and tonumber(part) == i and tonumber(of) == #sent, f[7])
        assert(id == nil or pid == id, "one id for all the parts")
        id = pid
        assert(#f[8] <= 480, "a part of " .. #f[8] .. " bytes")
        out[#out + 1] = f[8]
    end
    return table.concat(out, "\n")
end
local many = ns.Dictionary.Text()
for i = 1, 40 do many = many .. ("моёслово%d=очень длинная замена номер %d для проверки частей\n"):format(i, i) end
ns.Dictionary.SetText(many)
sent = {}
ns.SendDictionary(true)
assert(#sent > 3 and parts() == ns.Dictionary.UserLayer(), "the parts joined are the layer: " .. #sent)
-- a line longer than a part is not sent cut (another rule, or a broken one): left out, the player told once
local long = "~" .. ("(?:сказала?|говорит|пишет)"):rep(12) .. "=слишком длинная регулярка"
ns.Dictionary.SetText(many .. long .. "\n")
local toldLong, print0 = {}, print
print = function(t) toldLong[#toldLong + 1] = t end
sent = {}
ns.SendDictionary(true)
local kept = {}
for line in ns.Dictionary.UserLayer():gmatch("[^\n]+") do if line ~= long then kept[#kept + 1] = line end end
local withoutLong = table.concat(kept, "\n")
assert(#kept == 40 and ns.Dictionary.UserLayer():find(long, 1, true), "the long line is in the layer")
assert(parts() == withoutLong, "the rest goes whole")
-- left out alike of the frames, their id and the saved variables (read when the frames have not come)
assert(ns.db.dictionaryUser == withoutLong, "the saved variables keep the layer as sent")
local crcBytes = {}
for i = 1, #withoutLong do crcBytes[i] = withoutLong:byte(i) end
assert(sent[1]:find(("\31id=%04x;"):format(ns.Protocol.CRC16(crcBytes))), "the id is the sent layer's: " .. sent[1]:sub(1, 80))
ns.SendDictionary(true)
-- typed on, with pauses (each sends the layer 2 s after the last key): told once, not at every pause
for i = 1, 4 do
    ns.Dictionary.SetText(many .. long .. (" ещё"):rep(i) .. "\n")
    ns.SendDictionary(false)
end
print = print0
assert(#toldLong == 1 and toldLong[1]:find("длиннее 480 байт", 1, true), toldLong[1] or "not told")
-- the line as the chat shows it: its "|" doubled, or the chat takes them for markup
assert(toldLong[1]:find("(?:сказала?||говорит||пишет)", 1, true), toldLong[1])
-- a second long line is news
print = function(t) toldLong[#toldLong + 1] = t end
ns.Dictionary.SetText(many .. long .. "\n" .. long:gsub("слишком", "очень") .. "\n")
ns.SendDictionary(false)
print = print0
assert(#toldLong == 2 and toldLong[2]:find("длиннее 480 байт", 1, true), "a new long line: " .. #toldLong)
ns.Dictionary.Reset()
print("dictionary parts ok")

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
-- /bv off forgets the lines held for a quest voice-over: they are not read after /bv on
ns.db.cell, ns.db.rows = 2, 1                 -- /bv on sends the settings, the strip's place with them
CatQuestCore = { state = { playing = true } }
ns.Send("party", "Вася-Степи", "Orc", 2, "WARRIOR", "", "до выключения")
local print0 = print
print = function() end
ns.SetEnabled(false)
ns.Send("party", "Вася-Степи", "Orc", 2, "WARRIOR", "", "пока выключено")   -- the dictionary window's «Озвучить»
ns.SetEnabled(true)
print = print0
CatQuestCore = nil
sent = {}
ns.ReleaseHeld()
assert(#sent == 0, "nothing held over /bv off: " .. tostring(sent[1]))
-- with the addon off the strip takes nothing: what asks the companion says it is off, not its usual
-- word; the reset of the race voices waits for /bv on
do
    local said, push0, first0, now0 = {}, ns.Strip.Push, ns.Strip.PushFirst, ns.Strip.PushNow
    local pushed = {}
    ns.Strip.Push = function(p) pushed[#pushed + 1] = p end
    ns.Strip.PushFirst, ns.Strip.PushNow = ns.Strip.Push, ns.Strip.Push
    print = function(t) said[#said + 1] = t end
    ns.SetEnabled(false)
    pushed, said = {}, {}
    ns.ResetVoices(); ns.OpenLink("discord"); ns.CopyLink("discord"); ns.Replay(3); ns.TestVoice("Anna"); ns.Test()
    SlashCmdList.BARRENSVOICE("stop")
    tryBox._scripts.OnEnterPressed(tryBox)                 -- the dictionary window's «Озвучить»
    print = print0
    assert(#pushed == 0, "nothing for the strip while off: " .. tostring(pushed[1]))
    assert(#said == 8, "a word for each: " .. #said)
    assert(said[1]:find("когда вы её включите", 1, true) and ns.db.resetVoices, said[1])
    assert(said[2]:find("озвучка выключена", 1, true) and said[2]:find("discord.gg", 1, true), said[2])
    for i = 3, 6 do assert(said[i]:find("озвучка выключена", 1, true), said[i]) end
    assert(said[7]:find("и так выключена", 1, true), said[7])
    assert(said[8]:find("озвучка выключена", 1, true), said[8])
    print = function() end
    ns.SetEnabled(true)
    print = print0
    local reset = 0
    for _, p in ipairs(pushed) do if p:find("^reset\31") then reset = reset + 1 end end
    assert(reset == 1 and ns.db.resetVoices == nil, "the reset goes at /bv on, once: " .. reset)
    ns.Strip.Push, ns.Strip.PushFirst, ns.Strip.PushNow = push0, first0, now0
end
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
ns.Send("party", "Вася-Степи", "Orc", 2, "WARRIOR", "", "кто идёт в ОП?")
ns.Send("say", "Вася-Степи", "Orc", 2, "WARRIOR", "", "что тут?")
ns.Send("yell", "Вася-Степи", "Orc", 2, "WARRIOR", "", "что тут?")
ns.Send("party", "Вася-Степи", "Orc", 2, "WARRIOR", "", "привет, кто идёт?!")
assert(said(3) == "Вася спрашивает:\4 кто идёт в ОП?" and said(4) == "Вася спрашивает:\4 что тут?"
    and said(5) == "Вася кричит:\4 что тут?" and said(6) == "Вася пишет:\4 привет, кто идёт?!", said(3) .. " | " .. said(4) .. " | " .. said(5) .. " | " .. said(6))
assert(said(2) == "Вася\5 смеётся", said(2))                               -- an emote: a name never dropped
print("continue ok")

-- the place (sayWhere): with the verb, once per change of place or after a minute's quiet
do
    local clock0 = GetTime
    local at = 1000
    GetTime = function() return at end
    ns.db.sayWhere = true
    sent = {}
    local function say(kind, text, channel, seconds)
        at = at + (seconds or 5)
        ns.Send(kind, "Тралл-Степи", "Orc", 2, "SHAMAN", channel or "", text)
        return said(#sent)
    end
    local function eq(got, want) assert(got == want, ("got %q, want %q"):format(got, want)) end
    eq(say("guild", "всем привет", nil, 120), "Тралл пишет в гильдии:\4 всем привет")
    eq(say("guild", "как дела"), "Тралл пишет:\4 как дела")                      -- the same place: not again
    eq(say("guild", "кто в ОП?"), "Тралл спрашивает:\4 кто в ОП?")
    eq(say("channels", "продам сумки", "2. Торговля - Город"), "Тралл пишет в торговле:\4 продам сумки")
    eq(say("guild", "кто идёт?"), "Тралл спрашивает в гильдии:\4 кто идёт?")   -- back from Trade: again
    eq(say("say", "привет"), "Тралл говорит:\4 привет")                         -- no place of its own
    eq(say("guild", "я тут"), "Тралл пишет в гильдии:\4 я тут")                -- after a say line: again
    eq(say("guild", "ау", nil, 60), "Тралл пишет в гильдии:\4 ау")              -- a minute's quiet: again
    eq(say("guild", "ау", nil, 59), "Тралл пишет:\4 ау")
    eq(say("party", "пул"), "Тралл пишет в группе:\4 пул")
    eq(say("instance", "пул"), "Тралл пишет:\4 пул")                            -- a group's chat all the same
    eq(say("raid", "бафы"), "Тралл пишет в рейде:\4 бафы")
    eq(say("warning", "все в круг"), "Тралл объявляет рейду:\4 все в круг")
    eq(say("warning", "все из круга?"), "Тралл объявляет:\4 все из круга?")    -- an announcement asks nothing
    eq(say("officer", "собрание"), "Тралл пишет в офицерском чате:\4 собрание")
    eq(say("channels", "го", "1. Общий - Оргриммар"), "Тралл пишет в общем:\4 го")
    eq(say("channels", "го", "5. мойканал"), "Тралл пишет в канале мойканал:\4 го")
    eq(say("whisper", "привет"), "Тралл шепчет:\4 привет")
    eq(say("emote", "смеётся"), "Тралл\5 смеётся")
    -- without the verb: a comma
    ns.db.sayVerb = false
    eq(say("guild", "привет"), "Тралл, в гильдии:\4 привет")
    eq(say("guild", "ещё"), "Тралл:\4 ещё")
    ns.db.sayVerb = true
    -- off: no place at all
    ns.db.sayWhere = false
    eq(say("party", "пул", nil, 120), "Тралл пишет:\4 пул")
    eq(say("guild", "привет"), "Тралл пишет:\4 привет")
    GetTime = clock0
    print("place ok")
end

-- where the strip goes: the bottom (default), the top, or a place of one's own kept on the screen
assert(ns.DEFAULTS.stripPlace == "bottom", "the strip is at the bottom by default")
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

-- the radio buttons (UI.Radio): the voices' engine in «Голоса», the strip's place in the bridge section
local function radios(label)
    local found = {}
    for _, f in ipairs(frames) do
        local text = rawget(f, "label")
        if text and text._text == label and f._scripts.OnClick then found[#found + 1] = f end
    end
    return found
end
assert(#radios("Windows") == 1 and #radios("Расы") == 1 and #radios("Вверху") == 1, "each radio button made once")
local sapiRadio, f5Radio, topRadio = radios("Windows")[1], radios("Расы")[1], radios("Вверху")[1]
assert(sapiRadio._scripts.OnEnter and not topRadio._scripts.OnEnter, "a tooltip only where one is given")
local quietRadio = print
print = function() end
ns.db.voices = "f5"
sapiRadio._scripts.OnClick(sapiRadio)
assert(ns.db.voices == "sapi" and sapiRadio._checked and not f5Radio._checked, "Windows voices picked")
f5Radio._scripts.OnClick(f5Radio)
assert(ns.db.voices == "f5" and f5Radio._checked and not sapiRadio._checked, "race voices picked")
print = quietRadio
topRadio._scripts.OnClick(topRadio)
assert(ns.StripWindow.Pending().place == "top" and topRadio._checked and not radios("Внизу (обычно)")[1]._checked, "the top picked")
print("radio buttons ok")
-- «Что читать»: one choice over onlyVisible and onlyActiveTab
do
    local all, windows, tab = radios("Все включённые каналы, даже не показанные в чате")[1], radios("Что показывают окна чата (обычно)")[1],
        radios("Только выбранная вкладка")[1]
    assert(all and windows and tab and #radios("Все включённые каналы, даже не показанные в чате") == 1, "three radio buttons, made once")
    assert(ns.DEFAULTS.onlyVisible == true and ns.DEFAULTS.onlyActiveTab == false, "what the windows show, by default")
    local function picked() return (all._checked and "all" or "") .. (windows._checked and "windows" or "")
        .. (tab._checked and "tab" or "") end
    tab._scripts.OnClick(tab)
    assert(ns.db.onlyVisible == true and ns.db.onlyActiveTab == true and picked() == "tab", picked())
    all._scripts.OnClick(all)
    assert(ns.db.onlyVisible == false and ns.db.onlyActiveTab == false and picked() == "all", picked())
    windows._scripts.OnClick(windows)
    assert(ns.db.onlyVisible == true and ns.db.onlyActiveTab == false and picked() == "windows", picked())
    ns.db.onlyActiveTab = true                       -- saved so: the window shows it as such
    ns.Options.Refresh()
    assert(picked() == "tab" and ns.Options.ReadsNow() == "tab", picked())
    ns.db.onlyVisible = false                        -- off wins: the tab does not matter then
    ns.Options.Refresh()
    assert(picked() == "all", picked())
    ns.db.onlyVisible, ns.db.onlyActiveTab = false, false
    print("what to read ok")
end

-- the chat windows out of sight: transparent without the mouse; a line not read aloud shows its window.
-- No chat filter: the window's AddMessage gets the event and its arguments (ChatFrameOverrides.lua).
ChatFrame_AddMessageEventFilter = function() error("no chat filter is needed") end
local addFilter = ChatFrameUtil.AddMessageEventFilter
ChatFrameUtil.AddMessageEventFilter = function() error("no chat filter is needed") end
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
editBox.isGM = false                                    -- (the stub's other fields are functions)
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
editBox:SetAlpha(0.35)                                  -- the game, the message sent (Deactivate, "im" style)
settle(2)
assert(editBox:GetAlpha() == 0, "done typing: out of sight again")
ChatFrame1.IsMouseOver = function() return true end
settle(0.5)
assert(ChatFrame1:GetAlpha() == 1 and editBox:GetAlpha() == 0.35,
    "the mouse over the chat: the edit box nobody types in as the game shows it (\"im\" style), not brighter")
ChatFrame1.IsMouseOver = nil
settle(2)
editBox:SetAlpha(1)                                     -- the game: the newcomer's hint in the box
ChatFrame1.IsMouseOver = function() return true end
settle(0.5)
assert(editBox:GetAlpha() == 1, "shown again: as the game last set it, whatever it was (the newcomer's hint)")
ChatFrame1.IsMouseOver = nil
editBox:SetAlpha(0.35)                                  -- the game: the hint gone, the box dimmed again
settle(2)
-- a chat event's line as the chat window adds it: AddMessage(msg, r, g, b, id, accessID, typeID, event,
-- eventArgs, MessageFormatter), eventArgs SafePack'ed (n); an event the window does not show never gets here
local function args(text, guid, channel, base)
    return { text, "Вася-Степи", "", channel or "", "", "", 0, 0, base or "", 0, 1, guid, 0, false, n = 14 }
end
local function line(event, text, guid, frame)
    frame = frame or ChatFrame1
    frame:AddMessage("[Вася]: " .. text, 1, 1, 1, 1, 1, 1, event, args(text, guid), function(m) return m end)
end
line("CHAT_MSG_PARTY", "привет", "Player-1-2")
settle(0.3)
assert(ChatFrame1:GetAlpha() == 0, "a line read aloud: the window stays out of sight")
-- a General line read aloud: no flash either
ns.db.channels = true
ChatFrame1:AddMessage("[1. Общий] [Вася]: кто в ОП?", 1, 1, 1, 1, 1, 1, "CHAT_MSG_CHANNEL",
    args("кто в ОП?", "Player-1-3", "1. Общий", "Общий"))
settle(0.3)
assert(ChatFrame1:GetAlpha() == 0, "a General line read aloud: the window stays out of sight")
ns.db.chTrade = false
ChatFrame1:AddMessage("[2. Торговля] [Вася]: WTS", 1, 1, 1, 1, 1, 1, "CHAT_MSG_CHANNEL",
    args("WTS", "Player-1-3", "2. Торговля", "Торговля"))
settle(0.3)
assert(ChatFrame1:GetAlpha() == 1, "a channel switched off: the window shows")
ns.db.chTrade = nil
now = now + 11
settle(2)
ChatFrame1:AddMessage("Вы получили 5 серебра", 1, 1, 0, 1)            -- a system line: no event passed
settle(0.3)
assert(ChatFrame1:GetAlpha() == 1, "a system line is not read: the window shows")
-- a line leaves nothing behind (no mark for the next AddMessage): an addon's print right after a read line
-- shows the window
now = now + 11
settle(2)
line("CHAT_MSG_PARTY", "привет", "Player-1-2")
ChatFrame1:AddMessage("|cff40c0ffДругой аддон:|r готово")
settle(0.3)
assert(ChatFrame1:GetAlpha() == 1, "an addon's print right after a read line: shows")
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
assert(ns.ChatFade.Verdict("x", "CHAT_MSG_PARTY", setmetatable({}, { __index = function() error("no") end })) == "unknown",
    "arguments that cannot be looked at: shown, no error")
assert(ns.ChatFade.Verdict("x", 5, {}) == "other" and ns.ChatFade.Verdict("x", "CHAT_MSG_SAY", "args") == "other",
    "another addon's AddMessage with other arguments: not a chat event's line")
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
-- the group's lines (party, raid, raid warning, instance chat) too - on by default
assert(ns.DEFAULTS.fadeGroup == true, "the group's lines show the window by default")
for event, setting in pairs(ns.ChatFade.ALWAYS_SHOW) do
    assert(ns.EVENTS[event], "an event the addon reads: " .. event)
    assert(ns.DEFAULTS[setting] ~= nil, "a setting of its own: " .. setting)
end
ns.db.raid, ns.db.warning = true, true
for _, event in ipairs({ "CHAT_MSG_PARTY", "CHAT_MSG_RAID_WARNING" }) do
    ns.db.fadeGroup = true
    now = now + 20
    settle(2)
    line(event, "пул через 5", "Player-1-6")
    settle(0.3)
    assert(ChatFrame1:GetAlpha() == 1, event .. " with the option on: the window shows")
    ns.db.fadeGroup = false
    now = now + 20
    settle(2)
    line(event, "пул через 5", "Player-1-6")
    settle(0.3)
    assert(ChatFrame1:GetAlpha() == 0, event .. " with the option off: read, out of sight")
end
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
ChatFrame2:AddMessage("Hobby Warrior создает: Медный слиток.", 1, 1, 1, 1)
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
assert(editBox:GetAlpha() == 0.35, "and its edit box, as the game leaves it between messages")
ChatFrameUtil.AddMessageEventFilter, ChatFrame_AddMessageEventFilter = addFilter, nil
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
Co.Read({ beat = 0, stopped = 1090 }, 1100)
assert(Co.State() == "stopped", "the companion said it ended (a crash a moment ago): not running")
-- not running at login: the transparent chat stays visible - hidden and not read, a line would be lost
ns.db.fadeChat = true
ChatFrame1:SetAlpha(1)
ns.ChatFade.Apply()
now = now + 20                               -- past the 10 s the last line not read showed the window for
assert(not ns.ChatFade.Voiced())
assert(ChatFrame1:GetAlpha() == 1, "no companion: the chat is not faded")
Co.SayAtLogin()
assert(said[#said]:find("Прозрачный чат пока выключен"), tostring(said[#said]))
Co.Read({ beat = 1000 }, 1010)
ns.ChatFade.Apply()
for _ = 1, 10 do ns.ChatFade.Update(nil, 0.3) end
assert(ChatFrame1:GetAlpha() == 0, "running at login: faded")
ns.db.fadeChat = false
ns.ChatFade.Apply()
print = realPrint
print("companion ok")

-- the word at login: the welcome on the first run, a line after an update, then the companion's line
local welcome, plainPrint = {}, print
print = function(text) welcome[#welcome + 1] = text end
GetAddOnMetadata = function() return "0.4.0b1" end
ns.firstRun, ns.db.seenVersion = true, nil
ns.LoginWord()
assert(#welcome == 5 and welcome[1]:find("добро пожаловать") and welcome[2]:find("приложение%-компаньон")
    and welcome[4]:find("«Помощь»", 1, true) and welcome[5]:find("озвучка чата"), "welcome, then whether the reading works")
assert(ns.db.seenVersion == "0.4.0b1", "the version is kept")
ns.firstRun = false
welcome = {}
ns.LoginWord()
assert(#welcome == 1 and welcome[1]:find("озвучка чата"), "the same version again: only whether the reading works")
GetAddOnMetadata = function() return "0.4.0b2" end                   -- a test build: shown so, its release's news
welcome = {}
ns.LoginWord()
assert(#welcome == 3 and welcome[1]:find("обновление 0.4.0 beta 2: Barrens Voice ставится установщиком", 1, true)
    and welcome[2]:find("«Помощь»", 1, true), tostring(welcome[1]))
GetAddOnMetadata = function() return "9.9.9" end
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
ns.db.rate, ns.db.volume = 100, 100
print("sliders ok")

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
-- the chat window: a closed line comes to AddMessage with no chat filter called (the client calls them only
-- for a line addons can read): secret text and secret event arguments; it shows the window, and /bv debug
-- says why without looking at it
ns.db.fadeChat = true
local function closedLine(text, eventArgs)
    ChatFrame1:SetAlpha(1)
    now = now + 30
    for _ = 1, 10 do ns.ChatFade.Update(nil, 0.3) end
    assert(ChatFrame1:GetAlpha() == 0, "hidden before")
    pushed = {}
    ChatFrame1:AddMessage(text, 1, 1, 1, 1, 1, 1, "CHAT_MSG_PARTY", eventArgs, function(m) return m end)
    for _ = 1, 2 do ns.ChatFade.Update(nil, 0.3) end
    assert(ChatFrame1:GetAlpha() == 1, "a closed-chat line shows the window")
    assert(#pushed == 1 and pushed[1]:find("закрытый чат", 1, true) and pushed[1]:find("(закрытый текст)", 1, true)
        or not ns.db.debug, pushed[1] or "no debug line")
end
ns.db.debug = true
closedLine(SECRET, { SECRET, SECRET, "", "", "", "", 0, 0, "", 0, 1, SECRET, 0, false, n = 14 })
closedLine(SECRET, SECRET)                                   -- the whole table secret
assert(ns.ChatFade.Verdict("[Вася]: го", "CHAT_MSG_PARTY", { "го", SECRET, n = 14 }) == "closed", "a secret argument")
canaccesstable = function() return false end                 -- a table the addon may not index
assert(ns.ChatFade.Verdict("[Вася]: го", "CHAT_MSG_PARTY", { "го", n = 14 }) == "closed")
canaccesstable = nil
ns.db.debug = false
closedLine(SECRET, { SECRET, SECRET, "", "", "", "", 0, 0, "", 0, 1, SECRET, 0, false, n = 14 })
ns.db.fadeChat = false
-- the frame under the mouse with a secret name or parent: not looked at, no error
local secretChild = { GetName = function() return SECRET end, GetParent = function() return ChatFrame1 end }
local orphan = { GetName = function() return "SomeFrame" end, GetParent = function() return SECRET end }
GetMouseFoci = function() return { secretChild } end
assert(ns.ChatFade.MouseOnChat() == true, "a secret name: its parent, the chat window, still counts")
GetMouseFoci = function() return { orphan } end
assert(ns.ChatFade.MouseOnChat() == false, "a secret parent: not the chat's")
GetMouseFoci = function() return { SECRET } end
assert(ns.ChatFade.MouseOnChat() == false, "a secret frame: not the chat's")
GetMouseFoci = nil
ns.ChatFade.Apply()
print = quiet2
issecretvalue = nil
print("secret chat ok")

-- The strip's queue, driven by its OnUpdate: a fresh strip with the real Push / PushFirst / PushNow.
-- Each frame stays up HOLD (0.25 s), then, with nothing queued, the empty frame after IDLE_AFTER (0.5 s).
assert(loadfile("Strip.lua"))("BarrensVoice", ns)
local SQ = ns.Strip
ns.db.enabled, ns.db.stripPlace, ns.db.stripFrom, ns.db.cell, ns.db.rows, ns.db.voiceOff = true, "bottom", "left", 2, 1, nil
local encode = ns.Protocol.Encode
ns.Protocol.Encode = function(seq, payload, cells)             -- each frame's cells tagged with their payload
    local out, sent = encode(seq, payload, cells)
    out.payload = payload
    return out, sent
end
local n0 = #frames
SQ.Initialize()
local strip = frames[n0 + 1]
local tick = strip._scripts.OnUpdate
local t = 5000
GetTime = function() return t end
local function onStrip() local _, cells = SQ.Peek(); return cells and cells.payload end
local function waiting() return (SQ.Peek()) end
local function step(dt) t = t + dt; tick(); return onStrip() end
assert(onStrip() == "", "an empty frame from the start: the program sees the addon is there")
SQ.Push("a"); SQ.Push("b"); SQ.Push("c")
assert(step(0) == "a" and waiting() == 2)
assert(step(0.125) == "a", "held")
assert(step(0.125) == "b", "the next after 0.25 s")
assert(step(0.25) == "c" and waiting() == 0)
assert(step(0.25) == "c" and step(0.125) == "c", "nothing queued: up until 0.5 s")
assert(step(0.125) == "", "then the empty frame")
-- at most 60 waiting, the oldest dropped; a frame put first keeps the rest, dropping the oldest of them
for i = 1, 70 do SQ.Push("q" .. i) end
assert(waiting() == 60, "MAX_QUEUE: " .. waiting())
SQ.PushFirst("first")
assert(waiting() == 60)
assert(step(0) == "first" and step(0.25) == "q12", "ahead of the queue; q1..q11 dropped")
-- a stop: everything waiting dropped, shown at once (not after HOLD)
SQ.PushNow("stop")
assert(step(0.0625) == "stop" and waiting() == 0, "the stop at once")
assert(step(0.5) == "", "idle")
-- moving: the program is told on the strip where it is now, nothing else shown until the move
local later = {}
local after0 = C_Timer.After
C_Timer.After = function(_, f) later[#later + 1] = f end
local made = {}
rawset(strip, "CreateTexture", function()
    local tex = widget()
    tex.SetPoint = function(self, point) self._point = point end
    made[#made + 1] = tex
    return tex
end)
SQ.Push("before the move")
ns.db.stripPlace, ns.db.stripFrom = "top", "right"                    -- «Сохранить»: a new place, cells from the right
SQ.MoveTo()
assert(step(0) and onStrip():find("^control\31"), "the settings frame first: " .. tostring(onStrip()))
assert(#made > 0, "a frame longer than any before: new cells")
for _, tex in ipairs(made) do
    assert(tex._point == "TOPLEFT", "a frame painted before the move: all its cells from the old edge")
end
assert(step(0.5) and onStrip():find("^control\31"), "held until the move")
assert(#later == 1)
later[1]()
for _, tex in ipairs(made) do assert(tex._point == "TOPRIGHT", "moved: from the new edge") end
assert(step(0) == "before the move" and step(0.25):find("^control\31"), "then the queue, then the place told again")
C_Timer.After = after0
ns.db.stripPlace, ns.db.stripFrom = "bottom", "left"
SQ.Layout()
print("strip queue ok")

-- switched off: the hidden strip takes nothing (its OnUpdate does not run, all would play at /bv on)
local quiet3 = print
print = function() end
step(1)
ns.SetEnabled(false)
assert(not strip:IsShown() and waiting() == 0, "/bv off: hidden, nothing waiting")
for _ = 1, 30 do ns.SendControl() end
ns.OpenLink("discord")
ns.Test()
SQ.PushFirst("x"); SQ.PushNow("y")
assert(waiting() == 0, "nothing queued while off: " .. waiting())
ns.SetEnabled(true)
print = quiet3
assert(strip:IsShown() and step(0):find("^control\31"), "/bv on: fresh settings first")
assert(step(0.25):find("^dict\31"), "and the dictionary layer")
print("strip off ok")
