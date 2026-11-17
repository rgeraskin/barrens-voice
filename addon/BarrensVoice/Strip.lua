-- The strip: a black bar along the bottom edge of the screen (or the top, or a place of the player's
-- choosing: another addon may draw in the same corner), `cell` physical pixels high per row,
-- with near-black coloured cells on it that carry the latest chat line (Protocol.lua): the whole
-- bar reads as one dark line. A line's cells are held at least HOLD seconds so the reader catches
-- each one, then IDLE_AFTER the strip goes back to an empty frame (14 cells), which tells the
-- program the addon is there.
local _, ns = ...
local P = ns.Protocol

local S = {}
ns.Strip = S

local HOLD = 0.25      -- seconds each line stays up before the next queued one
local IDLE_AFTER = 0.5 -- then, with nothing queued, the strip goes back to an empty frame (the
                       -- program grabs the window 20 times a second: 0.25 s is enough for it)
local MAX_QUEUE = 60   -- lines waiting beyond this are dropped, oldest first (a /bv last of all 50
                       -- history lines must fit: at 4 lines a second they are up in under 15 s)

local frame, background, preview
local textures = {}
local painted = 0      -- cells coloured by the last paint
local perRow, total, unit, cellPx = 0, 0, 1, 2
local queue = {}
local lastShown = 0
local seq = math.random(0, 65535)
local moving = false   -- between telling the program of a new place and moving there
local fromRight = false -- the cells' direction as laid out (Layout), not as just saved: a frame
                        -- painted before the move keeps the old one for all its cells
local shown            -- the cells painted last (S.Peek, for the tests)

S.MIN_WIDTH = 200      -- physical pixels: a narrower strip holds too little of a line per row
-- The longest frame the strip must hold, in payload bytes: a part of the dictionary layer (480) with
-- its fields, or a chat line (255 bytes at most) with its name, channel and options, with room to
-- spare. Rows are added until it fits: a narrow strip is a thicker one (and a 1280-pixel screen
-- gets two rows: one held only 469 bytes).
S.NEED_BYTES = 560

--- Rows of cells a strip `width` physical pixels wide needs (at least the `rows` setting).
function S.RowsFor(width)
    local perRow = math.max(1, math.floor(width / ns.db.cell))
    return math.max(ns.db.rows or 1, math.ceil(P.CellsFor(S.NEED_BYTES) / perRow))
end

--- Cells run from the left edge rightwards by default, or from the right edge leftwards; the
--- program reads either.
local function Place(i)
    local t = textures[i]
    local col = (i - 1) % perRow
    local row = math.floor((i - 1) / perRow)
    t:ClearAllPoints()
    t:SetSize(cellPx * unit, cellPx * unit)
    if fromRight then
        t:SetPoint("TOPRIGHT", frame, "TOPRIGHT", -col * cellPx * unit, -row * cellPx * unit)
    else
        t:SetPoint("TOPLEFT", frame, "TOPLEFT", col * cellPx * unit, -row * cellPx * unit)
    end
end

--- Where the strip goes, in physical pixels of the screen: x, y (of its top left corner), width,
--- height. "bottom" (the default) and "top" span the screen; "custom" is the player's x, y and width,
--- kept on the screen: x and y as given (as far as a strip of the least width still fits), the width
--- cut to what is left of the screen after x. The arguments override the saved settings (the
--- settings window's preview).
function S.Geometry(place, x, y, width)
    local physW, physH = GetPhysicalScreenSize()
    place = place or ns.db.stripPlace or "bottom"
    if place == "custom" then
        local least = math.min(S.MIN_WIDTH, physW)
        x = math.max(0, math.min(math.floor(tonumber(x or ns.db.stripX) or 0), physW - least))
        width = math.floor(tonumber(width or ns.db.stripWidth) or physW)
        width = math.max(least, math.min(width, physW - x))
        local h = ns.db.cell * S.RowsFor(width)
        y = math.max(0, math.min(math.floor(tonumber(y or ns.db.stripY) or 0), physH - h))
        return x, y, width, h
    end
    local h = ns.db.cell * S.RowsFor(physW)
    if place == "bottom" then
        return 0, physH - h, physW, h
    end
    return 0, 0, physW, h
end

--- The strip's place as the program takes it: "x,y,width,height,screen width,screen height".
function S.Describe()
    local x, y, w, h = S.Geometry()
    local physW, physH = GetPhysicalScreenSize()
    return ("%d,%d,%d,%d,%d,%d"):format(x, y, w, h, physW, physH)
end

--- Size and place the strip in physical pixels: at scale 1 the screen is 768 units high.
function S.Layout()
    if not frame then return end
    local physW, physH = GetPhysicalScreenSize()
    local x, y, w, h = S.Geometry()
    unit = 768 / physH
    cellPx = ns.db.cell
    fromRight = ns.db.stripFrom == "right"
    perRow = math.floor(w / cellPx)
    total = perRow * math.floor(h / cellPx)
    frame:ClearAllPoints()
    frame:SetPoint("TOPLEFT", WorldFrame, "TOPLEFT", x * unit, -y * unit)
    frame:SetSize(w * unit, h * unit)
    for i = 1, #textures do Place(i) end
    ns.db.stripGeometry = S.Describe()   -- for a program started while the game runs
end

--- Move the strip to the place now in the settings. The program is told first, on the strip where
--- it is now (a frame ahead of the queue, held a second with nothing else shown, so no chat line is
--- shown where the program no longer looks); then the strip moves and says where it is from there.
function S.MoveTo()
    if not frame then return end
    S.PushFirst(ns.ControlPayload())
    moving = true
    lastShown = 0
    C_Timer.After(1, function()
        moving = false
        S.Layout()
        S.Push(ns.ControlPayload())
    end)
end

--- A bright frame around where the strip would go (the settings window's preview), under the strip
--- so its cells stay readable; nil hides it.
function S.Preview(place, x, y, width)
    if not frame then return end
    if not place then
        if preview then preview:Hide() end
        return
    end
    if not preview then
        preview = CreateFrame("Frame", nil, nil)            -- no parent, as the strip: above the UI
        preview:SetIgnoreParentScale(true)
        preview:SetScale(1)
        preview:SetFrameStrata("TOOLTIP")
        preview:SetFrameLevel(8990)
        preview:EnableMouse(false)
        local t = preview:CreateTexture(nil, "BACKGROUND")
        t:SetAllPoints()
        t:SetColorTexture(1, 0.5, 0, 0.85)
    end
    local px, py, pw, ph = S.Geometry(place, x, y, width)
    local pad = 3
    preview:ClearAllPoints()
    preview:SetPoint("TOPLEFT", WorldFrame, "TOPLEFT", (px - pad) * unit, -(py - pad) * unit)
    preview:SetSize((pw + 2 * pad) * unit, (ph + 2 * pad) * unit)
    preview:Show()
end

local function Paint(cells)
    for i = 1, #cells do
        local t = textures[i]
        if not t then
            t = frame:CreateTexture(nil, "OVERLAY")
            textures[i] = t
            Place(i)
        end
        local c = cells[i]
        t:SetColorTexture(P.LEVELS[c[1] + 1] / 255, P.LEVELS[c[2] + 1] / 255, P.LEVELS[c[3] + 1] / 255, 1)
        t:Show()
    end
    for i = #cells + 1, painted do textures[i]:Hide() end
    painted = #cells
    shown = cells
end

local idle = true

local function OnUpdate()
    local now = GetTime()
    if #queue == 0 then
        -- the coloured cells are only up while the program needs to read them
        if not idle and now - lastShown >= IDLE_AFTER then
            seq = (seq + 1) % 65536
            Paint((P.Encode(seq, "", total)))
            idle = true
        end
        return
    end
    if now - lastShown < HOLD or (moving and lastShown > 0) then return end
    Paint(table.remove(queue, 1))
    lastShown = now
    idle = false
end

-- A hidden strip (the addon switched off) runs no OnUpdate: what was queued then would all play at
-- the next /bv on (old test lines, a link clicked an hour ago). It takes nothing while hidden; the
-- addon sends fresh settings and the dictionary layer when it is switched on (ns.SetEnabled).
local function Taking()
    return frame ~= nil and frame:IsShown()
end

--- Queue a payload (UTF-8 text) for the strip (dropped while it is hidden).
function S.Push(payload)
    if not Taking() then return end
    seq = (seq + 1) % 65536
    local cells = P.Encode(seq, payload, total)
    queue[#queue + 1] = cells
    while #queue > MAX_QUEUE do table.remove(queue, 1) end
end

--- Put a payload ahead of everything queued and show it now (a stop must not wait its turn).
function S.PushNow(payload)
    if not Taking() then return end
    seq = (seq + 1) % 65536
    local cells = P.Encode(seq, payload, total)
    queue = { cells }
    lastShown = 0
end

--- Put a payload ahead of the queued ones, keeping them (a pause for CatQuest must not wait behind
--- chat lines, nor drop them as PushNow does).
function S.PushFirst(payload)
    if not Taking() then return end
    seq = (seq + 1) % 65536
    local cells = P.Encode(seq, payload, total)
    table.insert(queue, 1, cells)
    while #queue > MAX_QUEUE do table.remove(queue, 2) end
end

function S.SetShown(on)
    if not frame then return end
    frame:SetShown(on)
    if not on then queue = {} end
end

--- For the tests: how many frames wait, and the cells on the strip now.
function S.Peek()
    return #queue, shown
end

function S.Initialize()
    -- No parent: a child of WorldFrame is drawn under everything in UIParent whatever its strata (the
    -- action bars and the minimap covered it), and a child of UIParent hides with it (Alt+Z). A frame
    -- of its own is sorted with UIParent's by strata - TOOLTIP is above them - and stays up. Its
    -- points are still set on WorldFrame (the whole screen), which only places it.
    frame = CreateFrame("Frame", "BarrensVoiceStrip", nil)
    frame:SetIgnoreParentScale(true)
    frame:SetScale(1)
    frame:SetFrameStrata("TOOLTIP")
    frame:SetFrameLevel(9000)
    frame:EnableMouse(false)
    background = frame:CreateTexture(nil, "BACKGROUND")
    background:SetAllPoints()
    background:SetColorTexture(0, 0, 0, 1)
    S.Layout()
    -- Something on the strip from the start: an empty line under a fresh sequence number, so the
    -- reader sees the addon is there without saying anything.
    Paint((P.Encode(seq, "", total)))
    frame:SetScript("OnUpdate", OnUpdate)
    frame:RegisterEvent("DISPLAY_SIZE_CHANGED")
    frame:RegisterEvent("UI_SCALE_CHANGED")
    frame:SetScript("OnEvent", function()
        S.Layout()
        if ns.ControlPayload and ns.db then S.Push(ns.ControlPayload()) end   -- a new screen: a new place
    end)
    S.SetShown(ns.db.enabled)
end
