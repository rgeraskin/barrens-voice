-- The «Что нового» window (/bv news; by itself after an update with something big, News.lua): every entry the
-- installed version (the program's) has, newest first - the title, the version and the date, the items - in a
-- scrolling box, and under it the whole changelog on GitHub (UI.LinkRow: the address, «Копировать», «Открыть»). A
-- window of its own (UI.Window: it moves and closes on Escape), unlike the other *Window.lua files, which fill a
-- settings tab.
local _, ns = ...
local UI = ns.UI

local W = {}
ns.NewsWindow = W

W.WIDTH, W.HEIGHT = 580, 520
local SIDE = 22               -- the texts' inset from the window's sides
local BOX = 14                -- the box's
local TOP = -36               -- the line on top, under the title bar
local FOOT = 74               -- the box ends this far above the window's bottom: the changelog's line and row under it
W.CONTENT_W = W.WIDTH - 2 * BOX - 8 - 28   -- the scroll area's width: the box's padding, the scroll bar
W.BULLET = 16                 -- an item's indent: its marker sits in it
local GAP_ENTRY, GAP_ITEM = 18, 6

local TOP_TEXT = "Сверху — самое новое. Снова открыть это окно — /bv news или кнопкой на вкладке «Помощь» в "
    .. "настройках (/bv). Там же — куда писать об ошибках и идеях."
-- no entries: the companion has not written NewsData.lua yet (News.lua)
W.EMPTY = "Записи «Что нового» приносит Barrens Voice Launcher: запусти его, и после /reload они "
    .. "будут здесь."

local window, scroll, content
local pools = {}   -- the content's font strings by font, and the items' markers, reused at every show

--- The font string `n` of the `font` pool at (x, -y), `width` wide, with `text`; returns its height.
local function Put(font, n, x, y, width, text)
    pools[font] = pools[font] or {}
    local s = pools[font][n]
    if not s then
        s = content:CreateFontString(nil, "OVERLAY", font)
        s:SetJustifyH("LEFT")
        pools[font][n] = s
    end
    s:ClearAllPoints()
    s:SetPoint("TOPLEFT", x, -y)
    s:SetWidth(width)
    s:SetText(text)
    s:Show()
    return s:GetStringHeight() or 14
end

--- An item's marker (a small gold square: the game's font has no bullet) `n`, by the item's first line at -y.
local function Mark(n, y)
    pools.marks = pools.marks or {}
    local t = pools.marks[n]
    if not t then
        t = content:CreateTexture(nil, "ARTWORK")
        t:SetColorTexture(UI.GOLD[1], UI.GOLD[2], UI.GOLD[3], 0.9)
        t:SetSize(5, 5)
        pools.marks[n] = t
    end
    t:ClearAllPoints()
    t:SetPoint("TOPLEFT", 4, -(y + 5))
    t:Show()
end

--- "версия 0.4.0 — 18.11.2026"; a test build's as "0.4.1 beta 2"; no date until the release has one.
function W.Heading(entry)
    local version = "версия " .. ns.News.Shown(entry.version)
    return entry.date and (version .. " — " .. entry.date) or version
end

--- Lay `entries` out in the box, top down; returns the content's height.
function W.Fill(entries)
    for _, pool in pairs(pools) do
        for _, region in ipairs(pool) do region:Hide() end
    end
    local y, counts = 0, {}
    local function put(font, x, text)
        counts[font] = (counts[font] or 0) + 1
        y = y + Put(font, counts[font], x, y, W.CONTENT_W - x, text)
    end
    local marks = 0
    if #entries == 0 then put("GameFontHighlight", 0, W.EMPTY) end
    for i, e in ipairs(entries) do
        if i > 1 then y = y + GAP_ENTRY end
        put("GameFontNormalLarge", 0, e.title)
        y = y + 2
        put("GameFontDisableSmall", 0, W.Heading(e))
        for _, item in ipairs(e.items or {}) do
            y = y + GAP_ITEM
            marks = marks + 1
            Mark(marks, y)
            put("GameFontHighlight", W.BULLET, item)
        end
    end
    content:SetHeight(math.max(1, y))
    return y
end

local function Build()
    window = UI.Window("BarrensVoiceNews", "Что нового в Barrens Voice", W.WIDTH, W.HEIGHT, "FULLSCREEN_DIALOG")
    local _, h = UI.Text(window, "GameFontDisable", SIDE, TOP, W.WIDTH - 2 * SIDE, TOP_TEXT)
    local box = UI.Box(window)
    box:SetPoint("TOPLEFT", BOX, TOP - h - 8)
    box:SetPoint("BOTTOMRIGHT", -BOX, FOOT)
    scroll = CreateFrame("ScrollFrame", "BarrensVoiceNewsScroll", box, "UIPanelScrollFrameTemplate")
    scroll:SetPoint("TOPLEFT", 8, -8)
    scroll:SetPoint("BOTTOMRIGHT", -28, 8)
    content = CreateFrame("Frame", nil, scroll)
    content:SetSize(W.CONTENT_W, 1)
    scroll:SetScrollChild(content)
    -- the changelog: the line, then the row (the address in a box, «Копировать», «Открыть»), a row's height apart
    UI.Text(window, "GameFontHighlight", SIDE, -(W.HEIGHT - FOOT + 8), W.WIDTH - 2 * SIDE,
        "Подробный список изменений — на GitHub, на английском:")
    UI.LinkRow(window, SIDE, -(W.HEIGHT - 44), W.WIDTH - 2 * SIDE, "changelog")
end

--- Open the window on top, scrolled to the newest entry.
function W.Show()
    if not window then Build() end
    W.Fill(ns.News.Visible(ns.News.Installed()))
    scroll:SetVerticalScroll(0)
    window:Show()
    if window.Raise then window:Raise() end
end

function W.IsShown()
    return window ~= nil and window:IsShown()
end

function W.Hide()
    if window then window:Hide() end
end
