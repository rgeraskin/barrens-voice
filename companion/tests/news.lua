-- «Что нового» (News.lua, NewsWindow.lua): the entries and the program's version from the companion's NewsData.lua,
-- the first run (before the companion ran, too), an update with a big entry and with small ones, the setting, the
-- combat, the chat link (on a model of the clients' click path), seen kept over a login, a test build's release
-- entry, and the window's layout (with no news yet, too).
-- Run: mise run test-lua (from addon/BarrensVoice, it loadfiles the addon by relative path)

-- Widget stubs that remember where a region is put, its size, text and font, its parent and children.
local FONT = { GameFontNormalLarge = { 9, 18 }, GameFontDisableSmall = { 6, 12 }, GameFontHighlightSmall = { 6, 12 } }
local created = {}
local function widget(kind, parent, template)
    local w = { _kind = kind, _parent = parent, _font = template, _text = "", _shown = false, _checked = false,
                _scripts = {}, _points = {}, _events = {}, _regions = {} }
    created[#created + 1] = w
    if parent then table.insert(parent._regions, w) end
    return setmetatable(w, { __index = function(_, k)
        if k == "GetText" then return function(self) return self._text end end
        if k == "SetText" then return function(self, v) self._text = v or "" end end
        if k == "SetPoint" then return function(self, point, ...) self._points[point] = { ... } end end
        if k == "ClearAllPoints" then return function(self) self._points = {} end end
        if k == "SetWidth" then return function(self, v) self._w = v end end
        if k == "SetHeight" then return function(self, v) self._h = v end end
        if k == "SetSize" then return function(self, a, b) self._w, self._h = a, b end end
        if k == "GetWidth" then return function(self) return self._w or 100 end end
        if k == "GetHeight" then return function(self) return self._h or 100 end end
        if k == "GetStringWidth" then return function() return 100 end end
        if k == "GetStringHeight" then return function(self)
            -- about 7 px a letter and 14 a line (GameFontHighlight), wrapped at the string's width
            local text = tostring(self._text):gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", "")
            local letters = select(2, text:gsub("[^\128-\191]", ""))
            if letters == 0 then return 0 end
            local f = FONT[self._font] or { 7, 14 }
            return math.ceil(letters * f[1] / (self._w or math.huge)) * f[2]
        end end
        if k == "GetChecked" then return function(self) return self._checked end end
        if k == "SetChecked" then return function(self, v) self._checked = v end end
        if k == "IsShown" then return function(self) return self._shown end end
        if k == "SetShown" then return function(self, v)
            self._shown = v and true or false
            if v and self._scripts.OnShow then self._scripts.OnShow(self) end
        end end
        if k == "Show" then return function(self) self:SetShown(true) end end
        if k == "Hide" then return function(self)
            if self._shown and self._scripts.OnHide then self._scripts.OnHide(self) end
            self._shown = false
        end end
        if k == "SetScript" then return function(self, n, f) self._scripts[n] = f end end
        if k == "GetScript" then return function(self, n) return self._scripts[n] end end
        if k == "RegisterEvent" then return function(self, e) self._events[e] = true end end
        if k == "UnregisterEvent" then return function(self, e) self._events[e] = nil end end
        if k == "SetScrollChild" then return function(self, child) self._child = child end end
        if k == "SetFrameStrata" then return function(self, v) self._strata = v end end
        if k == "GetValue" then return function(self) return self._value or 100 end end
        if k == "SetValue" then return function(self, v)
            self._value = v
            if self._scripts.OnValueChanged then self._scripts.OnValueChanged(self, v) end
        end end
        if k == "CreateFontString" then return function(self, _, _, font) return widget("FontString", self, font) end end
        if k == "CreateTexture" then return function(self) return widget("Texture", self) end end
        return function() end
    end })
end
CreateFrame = function(kind, name, parent, template)
    local f = widget(kind, parent, template)
    if name then _G[name] = f end
    return f
end
UIParent, WorldFrame, Minimap, GameTooltip = widget("Frame"), widget("Frame"), widget("Frame"), widget("Frame")
UISpecialFrames, SlashCmdList, StaticPopupDialogs = {}, {}, {}
StaticPopup_Show, GameTooltip_Hide = function() end, function() end
YES, NO = "Да", "Нет"
tinsert = table.insert
GetPhysicalScreenSize = function() return 2360, 1640 end
GetTime = function() return 0 end
PanelTemplates_SelectTab, PanelTemplates_DeselectTab, PanelTemplates_TabResize = function() end, function() end, function() end
UnitGUID = function() return "me" end
BackdropTemplateMixin = {}
Settings = { RegisterCanvasLayoutCategory = function() return {} end, RegisterAddOnCategory = function() end }

-- C_Timer: kept until the test runs them, with their delays
local timers = {}
C_Timer = { After = function(seconds, f) timers[#timers + 1] = { seconds = seconds, f = f } end,
            NewTimer = function() return { Cancel = function() end } end, NewTicker = function() end }
local function runTimers()
    local due = timers
    timers = {}
    for _, t in ipairs(due) do t.f() end
    return due
end
local combat = false
InCombatLockdown = function() return combat end

-- The clients' click path for a chat link, the same in the forever and live branches: ChatFrameMixin:OnHyperlinkClick
-- -> SetItemRef -> LinkUtil.ProcessLink. The "addon" type's handler (ItemRefHandlersShared.lua) fires EventRegistry's
-- "SetItemRef" (each callback through securecallfunction: (owner, link, text, button, frame)) and counts the link
-- handled; any other type falls through to the ItemRefTooltip, or with Shift to the chat's edit box.
local callbacks = {}
EventRegistry = { RegisterCallback = function(self, event, func, owner)
    assert(type(event) == "string" and type(func) == "function" and type(owner) ~= "number", "RegisterCallback's contract")
    callbacks[event] = callbacks[event] or {}
    callbacks[event][owner] = func
    return owner
end }
LinkTypes = { AddOn = "addon" }
local tooltips, inserted, shift = 0, {}, false
local function SetItemRef(link, text, button, frame)
    if link:match("^([^:]*)") == LinkTypes.AddOn then
        for owner, func in pairs(callbacks.SetItemRef or {}) do func(owner, link, text, button, frame) end
        return
    end
    if shift then inserted[#inserted + 1] = text else tooltips = tooltips + 1 end
end
--- A click on the first link of a chat line, as the chat frame hands it on.
local function click(line, button)
    local data, shown = line:match("|H(.-)|h(.-)|h")
    assert(data, "a link in the line: " .. line)
    SetItemRef(data, "|H" .. data .. "|h" .. shown .. "|h", button or "LeftButton", "ChatFrame1")
end

GetAddOnMetadata = function(addon, field)    -- the addon's own version: only the welcome says it
    assert(addon == "BarrensVoice" and field == "Version")
    return "0.4.0b4"
end

local ns = {}
dofile("../../companion/tests/toc.lua")(ns)   -- every file, in the .toc's order (NewsData.lua: the stand-in, nil)
local N, W = ns.News, ns.NewsWindow
local said, realPrint = {}, print
local function out(...) realPrint(...) end
print = function(t) said[#said + 1] = t end

-- What the companion writes into NewsData.lua (bv/news.py): the program's version and the entries it shows, as
-- news.toml has them - newest first, the release in work without a date. The texts are made up, of real lengths.
local function items(n, base)
    local t = {}
    for i = 1, n do
        t[i] = ("%s %d: что ты заметишь и что делать."):format(base, i) .. (" Ещё немного текста."):rep(i % 4)
    end
    return t
end
local REAL = {
    { version = "0.4.0", kind = "big", title = "Установщик и обновления без хлопот",
      summary = "установщик с автообновлением, словарь онлайн, вкладка «Помощь» и шёпот Battle.net",
      items = items(10, "Новое") },
    { version = "0.3.0", date = "15.11.2026", kind = "big", title = "Ритейл и прозрачный чат",
      summary = "ритейл, прозрачный чат и галочка на каждый общий канал", items = items(9, "Ритейл") },
    { version = "0.2.1", date = "12.11.2026", kind = "small", title = "Одна речь на персонажа",
      summary = "несколько строк подряд от одного персонажа звучат одной речью", items = items(5, "Речь") },
    { version = "0.2.0", date = "11.11.2026", kind = "big", title = "Голоса рас из самой игры",
      summary = "голоса рас из русской озвучки самой игры", items = items(5, "Голоса") },
    { version = "0.1.0", date = "11.11.2026", kind = "big", title = "Первый выпуск (тогда — WoW Chat Voice)",
      summary = "первый выпуск", items = items(3, "Начало") },
}
local DATA = { version = "0.4.0b16", entries = REAL }
BarrensVoiceNewsData = DATA

local function fresh(db)
    ns.db = {}
    for k, v in pairs(ns.DEFAULTS) do ns.db[k] = v end
    for k, v in pairs(db or {}) do ns.db[k] = v end
    ns.Dictionary.Migrate(ns.db)
    ns.Dictionary.Rebuild()
end
--- A login (PLAYER_LOGIN's word) with the companion's news of `version` (none: nothing written yet) and the
--- timers after it; what the chat got.
local function login(version, firstRun)
    DATA.version = version
    BarrensVoiceNewsData = version and DATA or nil
    ns.firstRun = firstRun or false
    said = {}
    ns.LoginWord()
    runTimers()
    BarrensVoiceNewsData = DATA
    return said
end
local function news(lines)   -- the chat lines of News.lua (the companion's word is the other one)
    local out_ = {}
    for _, l in ipairs(lines) do if l:find("обновление", 1, true) then out_[#out_ + 1] = l end end
    return out_
end
local LINK = "|cffffd100|Haddon:BarrensVoice:news|h[Что нового]|h|r"
local HEAD = ns.ICON .. " " .. ns.PREFIX

do  -- the entries and the version: the companion's NewsData.lua (BarrensVoiceNewsData), nothing before it ran
    assert(N.Installed() == "0.4.0b16" and #N.Entries() == #REAL and N.Entries()[1] == REAL[1], "read from the global")
    BarrensVoiceNewsData = { version = "0.5.0", entries = { REAL[1], { version = "x", title = "t", summary = "s",
        items = {} }, { version = "0.3.0" }, "junk", REAL[2] } }
    local got = N.Entries()
    assert(#got == 2 and got[1] == REAL[1] and got[2] == REAL[2], "an entry not well formed is left out")
    for _, broken in ipairs({ { version = "?" }, { entries = REAL }, "0.4.0", 7 }) do
        BarrensVoiceNewsData = broken
        assert(N.Installed() == nil and #N.Visible(N.Installed()) == 0, "no version: nothing")
    end
    BarrensVoiceNewsData = { version = "0.4.0", entries = "junk" }
    assert(N.Installed() == "0.4.0" and #N.Entries() == 0, "no entries: none")
    BarrensVoiceNewsData = nil                               -- the stand-in the addon ships
    assert(N.Installed() == nil and #N.Entries() == 0, "before the companion ran: nothing")
    BarrensVoiceNewsData = DATA
    out("entries ok")
end

do  -- versions: a test build is older than its release, newer than the release before
    assert(N.Compare("0.4.0b5", "0.4.0") == -1 and N.Compare("0.4.0", "0.4.0b5") == 1)
    assert(N.Compare("0.3.0", "0.4.0b1") == -1 and N.Compare("0.4.0b10", "0.4.0b9") == 1)
    assert(N.Compare("0.4.1", "0.4.0") == 1 and N.Compare("0.10.0", "0.9.9") == 1)
    assert(N.Compare("?", "0.4.0") == nil and N.Compare(nil, "0.4.0") == nil)
    assert(N.Release("0.4.0b5") == "0.4.0" and N.Shown("0.4.0b5") == "0.4.0 beta 5" and N.Shown("0.4.0") == "0.4.0")
    assert(#N.Visible("?") == 0 and #N.Visible(nil) == 0, "no version known: nothing to show")
    out("versions ok")
end

do  -- the first run: the welcome, nothing of the news, every entry seen
    fresh()
    local lines = login("0.4.0b16", true)
    assert(lines[1]:find("добро пожаловать", 1, true) and lines[#lines]:find("приложение-компаньон", 1, true)
        and #news(lines) == 0, "the welcome and the companion's word only")
    assert(not W.IsShown(), "no window")
    for _, e in ipairs(REAL) do assert(ns.db.newsSeen[e.version], "seen: " .. e.version) end
    assert(#news(login("0.4.0b16")) == 0 and not W.IsShown(), "the next login: nothing")
    -- the first login before the companion wrote the news: decided when it has - still a newcomer, no history
    fresh()
    login(nil, true)
    assert(ns.db.newsSeen == nil and ns.db.newsFresh and not W.IsShown(), "nothing to mark yet")
    assert(#news(login(nil)) == 0 and ns.db.newsSeen == nil, "still nothing")
    assert(#news(login("0.4.0b16")) == 0 and not W.IsShown(), "the news come: nothing shown")
    for _, e in ipairs(REAL) do assert(ns.db.newsSeen[e.version], "seen: " .. e.version) end
    assert(ns.db.newsFresh == nil, "done with")
    out("first run ok")
end

do  -- an update with a big entry (an addon from before this list: only seenVersion): the window, after a while
    fresh({ seenVersion = "0.3.0" })
    DATA.version, ns.firstRun, said = "0.4.0b16", false, {}
    ns.LoginWord()
    assert(#said == 1 and said[1]:find("приложение-компаньон", 1, true) and not W.IsShown(),
        "first the companion's word, nothing else yet")
    assert(#timers == 1 and timers[1].seconds == N.DELAY and N.DELAY >= 3, "a few seconds after login")
    runTimers()
    assert(W.IsShown() and #news(said) == 0, "the window, no chat line")
    assert(ns.db.newsSeen["0.4.0"] and ns.db.newsSeen["0.3.0"] and ns.db.seenVersion == "0.4.0b16",
        "seen; the program's version kept")
    W.Hide()
    assert(#news(login("0.4.0b16")) == 0 and not W.IsShown(), "seen stays: the next login shows nothing")
    -- a tester on an earlier test build (the addon's 0.4.0b3, from before) had seen 0.4.0's one-liner, not the entry
    fresh({ seenVersion = "0.4.0b3" })
    login("0.4.0b16")
    assert(W.IsShown(), "a test build: its release's entry")
    W.Hide()
    -- the companion not run yet at this login: the version last seen stays, and the news wait for it
    fresh({ seenVersion = "0.3.0" })
    assert(#news(login(nil)) == 0 and not W.IsShown(), "no news yet")
    assert(ns.db.seenVersion == "0.3.0" and ns.db.newsSeen == nil, "nothing moved on")
    login("0.4.0b16")
    assert(W.IsShown() and ns.db.newsSeen["0.4.0"], "they come with the companion")
    W.Hide()
    out("big update ok")
end

local function entry(version, kind, summary, date)
    return { version = version, date = date or "20.11.2026", kind = kind, title = "Проверка " .. version,
             summary = summary, items = { "Пункт " .. version .. "." } }
end

do  -- only small entries: one chat line - the icon, «Barrens Voice:», the newest summary, the link
    fresh({ seenVersion = "0.4.0" })
    DATA.entries = { entry("0.4.2", "small", "словарь: ещё десяток слов"), entry("0.4.1", "small", "числа читаются точнее"),
                  unpack(REAL) }
    local lines = news(login("0.4.2"))
    assert(#lines == 1 and lines[1] == HEAD .. "обновление 0.4.2 — словарь: ещё десяток слов. " .. LINK, lines[1])
    assert(not W.IsShown(), "no window for small ones")
    assert(ns.db.newsSeen["0.4.2"] and ns.db.newsSeen["0.4.1"], "both seen")
    assert(#news(login("0.4.2")) == 0, "said once")
    -- a big one among them: the window
    DATA.entries = { entry("0.5.0", "big", "новое"), unpack(DATA.entries) }
    assert(#news(login("0.5.0")) == 0 and W.IsShown(), "big: the window")
    W.Hide()
    out("small update ok")
end

do  -- «Окно «Что нового» после обновлений» off: the chat line, big or not
    DATA.entries = { entry("0.6.0", "big", "большое и новое"), unpack(DATA.entries) }
    ns.db.newsWindow = false
    local lines = news(login("0.6.0"))
    assert(#lines == 1 and lines[1] == HEAD .. "обновление 0.6.0 — большое и новое. " .. LINK, tostring(lines[1]))
    assert(not W.IsShown() and ns.db.newsSeen["0.6.0"], "no window; seen")
    ns.db.newsWindow = true
    out("setting off ok")
end

do  -- in combat: nothing until PLAYER_REGEN_ENABLED, then a moment later; a new pull meanwhile waits again
    DATA.entries = { entry("0.7.0", "big", "бой"), unpack(DATA.entries) }
    combat = true
    login("0.7.0")
    assert(not W.IsShown() and not ns.db.newsSeen["0.7.0"], "not in combat")
    local waiter
    for _, f in ipairs(created) do if f._events.PLAYER_REGEN_ENABLED then waiter = f end end
    assert(waiter, "waits for the combat's end")
    waiter._scripts.OnEvent(waiter, "PLAYER_REGEN_ENABLED")
    assert(not waiter._events.PLAYER_REGEN_ENABLED, "once")
    assert(#timers == 1 and timers[1].seconds == N.AFTER_COMBAT, "a moment after it")
    runTimers()                                              -- the next pull came first
    assert(not W.IsShown() and waiter._events.PLAYER_REGEN_ENABLED, "in combat again: waits again")
    combat = false
    waiter._scripts.OnEvent(waiter, "PLAYER_REGEN_ENABLED")
    runTimers()
    assert(W.IsShown() and ns.db.newsSeen["0.7.0"], "out of combat: the window")
    W.Hide()
    -- the chat line waits as well
    DATA.entries = { entry("0.7.1", "small", "мелочь"), unpack(DATA.entries) }
    combat = true
    assert(#news(login("0.7.1")) == 0, "no line in combat")
    combat = false
    said = {}
    waiter._scripts.OnEvent(waiter, "PLAYER_REGEN_ENABLED")
    runTimers()
    assert(#news(said) == 1 and said[1]:find("мелочь", 1, true), "the line after the combat")
    out("combat ok")
end

do  -- the link: a click opens the window; Shift too, and nothing goes into the edit box; others' links are left alone
    assert(N.linked, "the link's callback is registered")
    DATA.entries = { entry("0.8.0", "small", "ссылка"), unpack(DATA.entries) }
    local line = news(login("0.8.0"))[1]
    assert(not W.IsShown())
    click(line)
    assert(W.IsShown() and tooltips == 0, "a click: the window, no item tooltip")
    W.Hide()
    shift = true
    click(line)
    assert(W.IsShown() and #inserted == 0 and tooltips == 0, "Shift: the window, nothing inserted")
    W.Hide()
    click(line, "RightButton")
    assert(W.IsShown(), "any button")
    W.Hide()
    shift = false
    click("|cff00ff00|Haddon:OtherAddon:news|h[Чужое]|h|r")
    assert(not W.IsShown(), "another addon's link: not ours")
    click("|cffffffff|Hitem:6948::::::::|h[Камень возвращения]|h|r")
    assert(not W.IsShown() and tooltips == 1, "an item link: the game's tooltip")
    -- retail's secret value (a click in a closed chat line) is not compared
    local SECRET = setmetatable({}, { __eq = function() error("a secret value cannot be compared") end })
    issecretvalue = function(v) return rawequal(v, SECRET) end
    N.OnLink(N, SECRET)
    issecretvalue = nil
    assert(not W.IsShown(), "secret: nothing")
    -- a client without the event: no link, the command instead
    local saved = EventRegistry
    EventRegistry = nil
    local bare = { Secret = ns.Secret, ICON = ns.ICON, PREFIX = ns.PREFIX }
    assert(loadfile("News.lua"))("BarrensVoice", bare)
    EventRegistry = saved
    assert(not bare.News.linked and bare.News.More() == "Что нового — /bv news.", bare.News.More())
    out("link ok")
end

do  -- a test build: its release's entry from the first build on, its own entry from that build on
    DATA.entries = { entry("0.9.0", "big", "выпуск"), entry("0.9.0b2", "small", "вторая сборка"), unpack(REAL) }
    DATA.entries[1].date = nil                                  -- not released yet
    fresh({ seenVersion = "0.4.0", newsSeen = { ["0.4.0"] = true, ["0.3.0"] = true } })
    login("0.9.0b1")
    assert(W.IsShown(), "the release's entry for its first test build")
    local function titles()
        local t = {}
        for _, r in ipairs(_G.BarrensVoiceNewsScroll._child._regions) do
            if r._shown and r._font == "GameFontNormalLarge" then t[#t + 1] = r._text end
        end
        return t
    end
    assert(titles()[1] == "Проверка 0.9.0" and titles()[2] == REAL[1].title, "a later test build's entry not shown yet")
    W.Hide()
    local lines = news(login("0.9.0b2"))
    assert(#lines == 1 and lines[1]:find("обновление 0.9.0 beta 2 — вторая сборка.", 1, true), tostring(lines[1]))
    W.Show()
    assert(titles()[1] == "Проверка 0.9.0b2" and titles()[2] == "Проверка 0.9.0",
        "its own entry above the release's: the new text first")
    assert(W.Heading(DATA.entries[1]) == "версия 0.9.0" and W.Heading(DATA.entries[2]) == "версия 0.9.0 beta 2 — 20.11.2026")
    W.Hide()
    table.insert(DATA.entries, 2, entry("0.9.0b4", "small", "четвёртая сборка"))
    lines = news(login("0.9.0b4"))
    assert(#lines == 1 and lines[1]:find("обновление 0.9.0 beta 4 — четвёртая сборка.", 1, true), tostring(lines[1]))
    W.Show()
    assert(titles()[1] == "Проверка 0.9.0b4" and titles()[2] == "Проверка 0.9.0b2" and titles()[3] == "Проверка 0.9.0",
        "the builds' entries newest first, then the release's")
    W.Hide()
    assert(#news(login("0.9.0")) == 0 and not W.IsShown(), "the release itself: nothing new")
    W.Show()
    assert(titles()[1] == "Проверка 0.9.0" and titles()[2] == "Проверка 0.9.0b4", "a release: its own entry on top")
    W.Hide()
    DATA.entries = REAL
    out("test builds ok")
end

do  -- the window: newest first, every item, nothing runs off the box or into another line; the footer in place
    DATA.version = "0.4.0b16"
    W.Show()
    assert(_G.BarrensVoiceNews._strata == "FULLSCREEN_DIALOG", "above the settings")
    local esc = false
    for _, name in ipairs(UISpecialFrames) do esc = esc or name == "BarrensVoiceNews" end
    assert(esc, "Escape closes it")
    local content = _G.BarrensVoiceNewsScroll._child
    local texts, marks = {}, {}
    for _, r in ipairs(content._regions) do
        if r._shown and r._kind == "FontString" then
            local p = r._points.TOPLEFT
            texts[#texts + 1] = { x = p[1], y = -p[2], w = r._w, h = r:GetStringHeight(), text = r._text }
        elseif r._shown and r._kind == "Texture" then
            marks[#marks + 1] = -r._points.TOPLEFT[2]
        end
    end
    table.sort(texts, function(a, b) return a.y < b.y end)
    local items = 0
    for _, e in ipairs(REAL) do items = items + #e.items end
    assert(#texts == 2 * #REAL + items and #marks == items, ("every title, heading and item: %d"):format(#texts))
    assert(texts[1].text == REAL[1].title and texts[2].text:find("^версия 0%.4%.0"), "the newest on top")
    for i, t in ipairs(texts) do
        assert(t.x >= 0 and t.x + t.w <= W.CONTENT_W, "within the box: " .. t.text)
        if i > 1 then
            local prev = texts[i - 1]
            assert(prev.y + prev.h <= t.y, ("«%s» runs into «%s»"):format(prev.text, t.text))
        end
    end
    assert(content._h == texts[#texts].y + texts[#texts].h, "the box scrolls to the last line")
    for _, y in ipairs(marks) do
        local at
        for _, t in ipairs(texts) do if t.x == W.BULLET and y >= t.y and y + 5 <= t.y + 14 then at = t end end
        assert(at, "a marker by an item's first line: " .. y)
    end
    -- the window: the line on top, the box, the changelog's line and row - in this order, inside the window
    local window = _G.BarrensVoiceNews
    local top, foot, row
    for _, r in ipairs(window._regions) do
        if r._kind == "FontString" and r._text:find("^Сверху") then top = r end
        if r._kind == "FontString" and r._text:find("^Подробный список") then foot = r end
        if r._text == "Открыть" then row = r end
    end
    local box = window._regions[#window._regions]
    for _, r in ipairs(window._regions) do if r._points.BOTTOMRIGHT then box = r end end
    local topEnd = -top._points.TOPLEFT[2] + top:GetStringHeight()
    local boxTop, boxBottom = -box._points.TOPLEFT[2], W.HEIGHT - box._points.BOTTOMRIGHT[2]
    local footTop = -foot._points.TOPLEFT[2]
    assert(topEnd < boxTop and boxBottom - boxTop >= 300, ("the box under the top line, tall enough: %d"):format(boxBottom - boxTop))
    assert(boxBottom < footTop and footTop + foot:GetStringHeight() <= -row._points.TOPLEFT[2], "the footer under the box")
    assert(-row._points.TOPLEFT[2] + 22 <= W.HEIGHT - 8, "the row inside the window")
    assert(row._points.TOPLEFT[1] + 76 <= W.WIDTH - 8 and foot._w + foot._points.TOPLEFT[1] <= W.WIDTH - 8,
        "nothing past the right edge")
    W.Hide()
    out("window layout ok")
end

do  -- the window before the companion wrote the news: one line, where they come from
    BarrensVoiceNewsData = nil
    W.Show()
    local shown = {}
    for _, r in ipairs(_G.BarrensVoiceNewsScroll._child._regions) do
        if r._shown and r._kind == "FontString" then shown[#shown + 1] = r._text end
    end
    assert(#shown == 1 and shown[1] == W.EMPTY, "only that line: " .. tostring(shown[1]))
    assert(not W.EMPTY:find("→", 1, true) and not W.EMPTY:find("–", 1, true), "the game's font has them not")
    W.Hide()
    BarrensVoiceNewsData = DATA
    out("window without news ok")
end

do  -- the settings: the check box on «Общее», the button on «Помощь»; /bv news and /bv help
    fresh()
    ns.Options.Open("help")
    local check, button
    for _, f in ipairs(created) do
        local label = rawget(f, "label")
        if label and label._text == "Окно «Что нового» после обновлений" then check = f end
        if f._kind == "Button" and f._text == "Что нового" then button = f end
    end
    assert(check and button, "the check box and the button")
    rawget(check, "refresh")()
    assert(check._checked, "on by default")
    check:SetChecked(false)
    check._scripts.OnClick(check)
    assert(ns.db.newsWindow == false, "the setting off")
    button._scripts.OnClick(button)
    assert(W.IsShown(), "«Что нового» on «Помощь» opens the window")
    W.Hide()
    SlashCmdList.BARRENSVOICE("  news ")
    assert(W.IsShown(), "/bv news")
    W.Hide()
    SlashCmdList.BARRENSVOICE("Что нового")
    assert(W.IsShown(), "/bv Что нового")
    W.Hide()
    said = {}
    SlashCmdList.BARRENSVOICE("help")
    local help = table.concat(said, "\n")
    assert(help:find("/bv news", 1, true) and help:find("/bv что нового", 1, true), "/bv help names it")
    out("settings ok")
end

print = realPrint
