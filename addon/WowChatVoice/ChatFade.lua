-- The chat windows out of sight (a setting, off by default): the chat is read aloud, so its lines
-- need not catch the eye. The windows - text, background, tabs, the edit box (faded on its own: in
-- the classic chat style it is always up and not inside the window) - stay transparent until
-- the mouse is over them or the player types. A line the program does not read shows its window
-- for REVEAL seconds: a system message, loot, a channel switched off, one's own line, an addon's
-- print - what is not heard must still be seen.
--
-- Transparency is SetAlpha on the chat frames and on the dock (GENERAL_CHAT_DOCK): the game sets
-- the alpha of their textures, tabs and buttons, never of the frames themselves, so nothing fights
-- over it. Which lines are read: a chat filter - called for each window about to show a line, with
-- the event, before it is shown - marks the window with whether the addon reads that line (the
-- same rule as for sending it, ns.Reads); the window's AddMessage right after takes the mark. An
-- AddMessage with no mark (an addon's print, a message not from a chat event) is not read. Only the
-- tab on screen counts: a line in a tab that is not the one shown shows nothing (unseen without the
-- fading too: the game flashes the tab) - so the combat log in the background, with crafting nearby
-- every few seconds, does not keep the chat up; switched to, its lines show it like any other.
-- The mouse counts only where nothing else is over the chat: IsMouseOver knows the rectangle, not
-- that a map or a bag lies on it - the frame really under the mouse (GetMouseFoci) tells.
local _, ns = ...

local F = {}
ns.ChatFade = F

local FADE_IN = 0.15   -- seconds to appear
local FADE_OUT = 0.5   -- seconds to disappear
local HIDE_DELAY = 1   -- seconds after the mouse leaves before the window fades
F.REVEAL = 10          -- seconds a line not read aloud keeps its window up
local MARK_FOR = 0.5   -- seconds a filter's mark waits for its AddMessage

local hiddenFor, revealUntil, marks, hooked = {}, {}, {}, {}
local driver

local function Shown(f)
    return f and f:IsVisible()
end

local CHAT_NAMES = { "^ChatFrame", "^GeneralDockManager", "^FloatingChatFrame", "^ChatAlertFrame" }

--- Whether the mouse is free to count for the chat: the frame under it is part of the chat (a window,
--- its tab, edit box, buttons, the tab strip) or nothing is (the world) - not another window over it.
function F.MouseOnChat()
    local focus
    if GetMouseFoci then
        local foci = GetMouseFoci()
        focus = foci and foci[1]
    elseif GetMouseFocus then
        focus = GetMouseFocus()
    end
    if not focus or focus == WorldFrame then return true end
    local f = focus
    while f do
        local name = f.GetName and f:GetName()
        if type(name) == "string" then
            for _, pattern in ipairs(CHAT_NAMES) do
                if name:find(pattern) then return true end
            end
        end
        f = f.GetParent and f:GetParent() or nil
    end
    return false
end

--- The mouse over the window, its tab strip, side buttons or edit box (and nothing else over them),
--- or the player typing.
local function FrameWanted(cf, mouseFree)
    local eb = cf.editBox
    if Shown(eb) and eb:HasFocus() then return true end
    if cf.ResizeButton and cf.ResizeButton:GetButtonState() == "PUSHED" then return true end
    if not mouseFree then return false end
    if cf:IsMouseOver(28, -2, -2, 2) then return true end
    if Shown(cf.buttonFrame) and cf.buttonFrame:IsMouseOver() then return true end
    return Shown(eb) and eb:IsMouseOver() or false
end

local function DockWanted(dock, mouseFree)
    if mouseFree and dock:IsMouseOver(10, -10, 0, 10) then return true end
    local overflow = dock.overflowButton
    return overflow and overflow.list and overflow.list:IsShown() or false
end


local function Step(frame, wanted, elapsed)
    local a = frame:GetAlpha()
    if wanted then
        hiddenFor[frame] = 0
        if a < 1 then frame:SetAlpha(math.min(1, a + elapsed / FADE_IN)) end
    else
        local t = (hiddenFor[frame] or 0) + elapsed
        hiddenFor[frame] = t
        if t >= HIDE_DELAY and a > 0 then frame:SetAlpha(math.max(0, a - elapsed / FADE_OUT)) end
    end
end

--- Show a window for REVEAL seconds (docked: with its tab strip) - if it is the one on screen (not a
--- tab in the background); returns whether it showed.
function F.Reveal(cf)
    local untilTime = GetTime() + F.REVEAL
    local dock = GENERAL_CHAT_DOCK
    if cf.isDocked and dock then
        local selected = FCFDock_GetSelectedWindow and FCFDock_GetSelectedWindow(dock)
        if selected and selected ~= cf then return false end
        revealUntil[dock] = untilTime
    end
    revealUntil[cf] = untilTime
    return true
end

local function OnAddMessage(self, text)
    local mark = marks[self]
    marks[self] = nil
    if mark and mark.read and GetTime() - mark.at <= MARK_FOR then return end
    if ns.db and ns.db.fadeChat and F.Reveal(self) then
        if ns.db.debug then        -- /wcv debug: which line showed the window, and why
            local line = tostring(text):gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", ""):gsub("|H.-|h(.-)|h", "%1")
            ns.Diag(("окно чата %s показано: %s — %s"):format(self.GetName and self:GetName() or "?",
                mark and "строку компаньон не читает" or "строка не из события чата (вывод аддона?)",
                ns.Protocol.TrimUTF8(line, 90)))
        end
    end
end

local function Hook(cf)
    if cf and not hooked[cf] and cf.AddMessage then
        hooksecurefunc(cf, "AddMessage", OnAddMessage)
        hooked[cf] = true
    end
end

--- The chat filter: never hides a line, only marks the window with whether the addon reads it.
function F.Filter(frame, event, _, _, ...)
    if ns.askingFilters then return false end    -- Core's "is it visible" check calls the filters too
    marks[frame] = { read = ns.Reads(event, (select(10, ...))), at = GetTime() }
    return false
end

function F.Update(_, elapsed)
    local now, dock = GetTime(), GENERAL_CHAT_DOCK
    local moving = MOVING_CHATFRAME and true or false
    local mouseFree = F.MouseOnChat()
    -- docked windows share one place and one tab strip: wanted together
    local dockWanted = moving
        or (dock and ((revealUntil[dock] or 0) > now or (Shown(dock) and DockWanted(dock, mouseFree)))) or false
    for _, name in ipairs(CHAT_FRAMES or {}) do
        local cf = _G[name]
        if cf and cf.isDocked and cf:IsShown() and FrameWanted(cf, mouseFree) then
            dockWanted = true
            break
        end
    end
    for _, name in ipairs(CHAT_FRAMES or {}) do
        local cf = _G[name]
        if cf then
            Hook(cf)                                  -- whisper windows opened later
            local wanted = moving or (cf.isDocked and dockWanted) or (revealUntil[cf] or 0) > now
                or (cf:IsShown() and FrameWanted(cf, mouseFree))
            Step(cf, wanted, elapsed)
            -- the edit box too: in the classic chat style it is always up and not inside the window
            local eb = cf.editBox
            if eb and eb.SetAlpha then Step(eb, wanted or (eb.HasFocus and eb:HasFocus()) or false, elapsed) end
        end
    end
    if dock then Step(dock, dockWanted, elapsed) end
end

local function ShowAll()
    for _, name in ipairs(CHAT_FRAMES or {}) do
        local cf = _G[name]
        if cf then
            cf:SetAlpha(1)
            if cf.editBox and cf.editBox.SetAlpha then cf.editBox:SetAlpha(1) end
        end
    end
    if GENERAL_CHAT_DOCK then GENERAL_CHAT_DOCK:SetAlpha(1) end
    wipe(hiddenFor)
end

--- Start or stop fading as the setting (and the addon's main switch) says.
function F.Apply()
    if not driver then return end
    if ns.db.fadeChat and ns.db.enabled then
        driver:SetScript("OnUpdate", F.Update)
    else
        driver:SetScript("OnUpdate", nil)
        ShowAll()
    end
end

function F.Initialize()
    driver = CreateFrame("Frame")
    local seen = {}
    local function Watch(event)
        if not seen[event] then
            seen[event] = true
            ChatFrame_AddMessageEventFilter(event, F.Filter)
        end
    end
    -- the events the addon reads, and every other the chat windows show; the channels' own messages
    -- (CHAT_MSG_CHANNEL: General, Trade...) are in no ChatTypeGroup list - the windows take them by
    -- channel - so without the first loop each read General line showed the window
    for event in pairs(ns.EVENTS or {}) do Watch(event) end
    for _, events in pairs(ChatTypeGroup or {}) do
        for _, event in ipairs(events) do Watch(event) end
    end
    for _, name in ipairs(CHAT_FRAMES or {}) do Hook(_G[name]) end
    F.Apply()
end
