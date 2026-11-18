-- The chat windows out of sight (a setting, off by default): the chat is read aloud, so its lines
-- need not catch the eye. The windows - text, background, tabs, the edit box (faded on its own: in
-- the "im" chat style it stays up between messages, under the window) - stay transparent until
-- the mouse is over them or the player types. A line the program does not read shows its window
-- for REVEAL seconds: a system message, loot, a channel switched off, one's own line, an addon's
-- print - what is not heard must still be seen. Only while the companion was running at login (or
-- the last /reload): hidden and not read aloud, a line would be lost - a companion started later
-- makes the chat transparent at the next /reload.
--
-- Transparency is SetAlpha on the chat frames and on the dock (GENERAL_CHAT_DOCK): the game sets
-- the alpha of their textures, tabs and buttons, never of the frames themselves, so nothing fights
-- over it. The edit box is the exception: the game sets its alpha itself (1 while the player types,
-- 0.35 after a message in the "im" style, hidden in "classic", 1 with the newcomer's hint;
-- ChatFrameEditBox.lua) - shown, it comes back to what the game last set (HookEditBox), not to 1. Which lines are read: the chat window hands a chat event's line to its AddMessage with
-- the event and the event's arguments (ChatFrameOverrides.lua, MessageEventHandler: AddMessage(msg,
-- r, g, b, id, accessID, typeID, event, eventArgs, MessageFormatter), Forever and retail alike) -
-- only for a line it shows, after its filters and its channel and whisper checks - and the hook asks
-- ns.Reads of them (the same rule as for sending it). An AddMessage without them (an addon's print, a
-- system message, loot) is not read. Retail's closed chat comes as secret values: not looked at, not
-- read (no chat filter could tell: the client calls addons' filters only for a line they can read,
-- ChatFrameFilters.lua). Only the tab on screen counts: a line in a tab that is not the one shown
-- shows nothing (unseen without the fading too: the game flashes the tab) - so the combat log in the
-- background, with crafting nearby every few seconds, does not keep the chat up; switched to, its
-- lines show it like any other.
-- The mouse counts only where nothing else is over the chat: IsMouseOver knows the rectangle, not
-- that a map or a bag lies on it - the frame really under the mouse (GetMouseFoci) tells.
local _, ns = ...

local F = {}
ns.ChatFade = F

local FADE_IN = 0.15   -- seconds to appear
local FADE_OUT = 0.5   -- seconds to disappear
local HIDE_DELAY = 1   -- seconds after the mouse leaves before the window fades
local EDIT_IDLE = 0.35 -- the game's alpha of an edit box nobody types in (ChatFrameEditBox.lua, Deactivate)
F.REVEAL = 10          -- seconds a line not read aloud keeps its window up

local hiddenFor, revealUntil, hooked = {}, {}, {}
local driver

local function Shown(f)
    return f and f:IsVisible()
end

local CHAT_NAMES = { "^ChatFrame", "^GeneralDockManager", "^FloatingChatFrame", "^ChatAlertFrame" }

--- Whether the mouse is free to count for the chat: the frame under it is part of the chat (a window,
--- its tab, edit box, buttons, the tab strip) or nothing is (the world) - not another window over it.
--- On retail a frame's name and parent can be secret (GetName, GetParent: SecretReturnsForAspect): such
--- a frame is not looked at and counts as not the chat's.
function F.MouseOnChat()
    local ok, focus = pcall(function()
        if GetMouseFoci then
            local foci = GetMouseFoci()
            return not ns.Secret(foci) and type(foci) == "table" and foci[1] or nil
        end
        return GetMouseFocus and GetMouseFocus() or nil
    end)
    if not ok or ns.Secret(focus) then return false end
    if not focus or focus == WorldFrame then return true end
    -- (called on every frame while the chat is hidden: no closure per frame looked at)
    local f = focus
    while f and not ns.Secret(f) and type(f) == "table" do
        local fine, name = pcall(f.GetName or error, f)
        if fine and not ns.Secret(name) and type(name) == "string" then
            for _, pattern in ipairs(CHAT_NAMES) do
                if name:find(pattern) then return true end
            end
        end
        local up, parent = pcall(f.GetParent or error, f)
        f = up and parent or nil
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


-- The edit box's alpha as the game last set it (ChatFrameEditBox.lua: 0.35 when a message is sent, 1 while
-- typing, 1 with the newcomer's hint - whatever the client does), so that shown again it is as the game left
-- it; a hook on its SetAlpha records the game's calls, ours are made with `ours` up and not recorded.
local gameAlpha, ours = {}, false

local function HookEditBox(eb)
    if eb and not hooked[eb] and eb.SetAlpha and eb.GetAlpha then
        gameAlpha[eb] = eb:GetAlpha()
        hooksecurefunc(eb, "SetAlpha", function(self, alpha)
            if not ours and type(alpha) == "number" then gameAlpha[self] = alpha end
        end)
        hooked[eb] = true
    end
end

--- The edit box's alpha when shown: 1 while the player types, else as the game last set it (EDIT_IDLE when
--- that is not known).
local function EditBoxAlpha(eb)
    if (eb.HasFocus and eb:HasFocus()) or eb.isGM then return 1 end
    return gameAlpha[eb] or EDIT_IDLE
end

--- Fade a frame towards `top` (1 unless given) when wanted, to nothing when not.
local function Step(frame, wanted, elapsed, top)
    local a = frame:GetAlpha()
    top = top or 1
    if wanted then
        hiddenFor[frame] = 0
        if a < top then frame:SetAlpha(math.min(top, a + elapsed / FADE_IN)) elseif a > top then frame:SetAlpha(top) end
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

-- Events whose lines show the window though the companion reads them, if the player asked: setting.
-- (Of the group's chat, the events Core.lua's EVENTS reads. One's own whispers, CHAT_MSG_WHISPER_INFORM and
-- CHAT_MSG_BN_WHISPER_INFORM, are read only with «Свои сообщения»: else they show the window as unread lines.)
local ALWAYS_SHOW = { CHAT_MSG_WHISPER = "fadeWhisper", CHAT_MSG_BN_WHISPER = "fadeWhisper",
    CHAT_MSG_WHISPER_INFORM = "fadeWhisper", CHAT_MSG_BN_WHISPER_INFORM = "fadeWhisper",
    CHAT_MSG_GUILD = "fadeGuild", CHAT_MSG_OFFICER = "fadeGuild",
    CHAT_MSG_PARTY = "fadeGroup", CHAT_MSG_PARTY_LEADER = "fadeGroup", CHAT_MSG_RAID = "fadeGroup",
    CHAT_MSG_RAID_LEADER = "fadeGroup", CHAT_MSG_RAID_WARNING = "fadeGroup", CHAT_MSG_INSTANCE_CHAT = "fadeGroup",
    CHAT_MSG_INSTANCE_CHAT_LEADER = "fadeGroup" }
F.ALWAYS_SHOW = ALWAYS_SHOW   -- for the tests

--- What becomes of a line a chat window shows: "read" (the companion reads it), "skipped" (a chat
--- event's line it does not read), "closed" (retail's closed chat, secret), "other" (no chat event's:
--- an addon's print, a system message) or "unknown" (its arguments could not be looked at).
local function Verdict(text, event, args)
    if ns.Secret(text, event, args) then return "closed" end
    if type(event) ~= "string" or event:sub(1, 9) ~= "CHAT_MSG_" or type(args) ~= "table" then return "other" end
    local ok, verdict = pcall(function()
        local canaccesstable = rawget(_G, "canaccesstable")
        if canaccesstable and not canaccesstable(args) then return "closed" end
        -- the event's arguments: text (1), sender (2), the channel's "2. Торговля" (4), its base name (9), GUID (12),
        -- a Battle.net friend's whisper's bnSenderID (13; Core.lua drops the line when it is secret; one's own
        -- whisper's, the recipient's, is not looked at)
        local message, channelString, baseName, guid = args[1], args[4], args[9], args[12]
        if ns.Secret(message, args[2], channelString, baseName, guid) then return "closed" end
        if event == "CHAT_MSG_BN_WHISPER" and ns.Secret(args[13]) then return "closed" end
        -- (a Battle.net friend who cannot be told is not read: Core.lua drops the line, so it shows the window)
        local bnSenderID = event == "CHAT_MSG_BN_WHISPER" and args[13] or nil
        return ns.Reads(event, guid, message, baseName, channelString, bnSenderID) and "read" or "skipped"
    end)
    return ok and verdict or "unknown"
end
F.Verdict = Verdict   -- for the tests

local REASONS = {
    read = "так просили в настройках (шёпот, гильдия или группа)",
    skipped = "строку компаньон не читает",
    closed = "закрытый чат (подземелье, рейд, PvP), компаньону не передать",
    other = "строка не из события чата (вывод аддона?)",
    unknown = "строку не удалось разобрать",
}

local function OnAddMessage(self, text, _, _, _, _, _, _, event, args)
    if not (ns.db and ns.db.fadeChat) then return end
    local verdict = Verdict(text, event, args)
    local asked = verdict == "read" and ALWAYS_SHOW[event] and ns.db[ALWAYS_SHOW[event]]
    if verdict == "read" and not asked then return end
    if F.Reveal(self) and ns.db.debug then        -- /bv debug: which line showed the window, and why
        local line = "(закрытый текст)"            -- a secret one (retail) cannot be looked at
        if not ns.Secret(text) then
            -- (a Battle.net friend's |K…|k, which the chat shows as their real name, is left out - and with no
            -- end mark seen, the rest of the line from it)
            line = tostring(text):gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", ""):gsub("|K.-|k", ""):gsub("|K.*", "")
                :gsub("|H.-|h(.-)|h", "%1")
        end
        ns.Diag(("окно чата %s показано: %s — %s"):format(self.GetName and self:GetName() or "?", REASONS[verdict],
            ns.Protocol.TrimUTF8(line, 90)))
    end
end

local function Hook(cf)
    if cf and not hooked[cf] and cf.AddMessage then
        hooksecurefunc(cf, "AddMessage", OnAddMessage)
        hooked[cf] = true
    end
    if cf then HookEditBox(cf.editBox) end
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
            -- the edit box too: in the "im" chat style it stays up between messages, under the window
            local eb = cf.editBox
            if eb and eb.SetAlpha then
                ours = true
                Step(eb, wanted or (eb.HasFocus and eb:HasFocus()) or false, elapsed, EditBoxAlpha(eb))
                ours = false
            end
        end
    end
    if dock then Step(dock, dockWanted, elapsed) end
end

local function ShowAll()
    for _, name in ipairs(CHAT_FRAMES or {}) do
        local cf = _G[name]
        if cf then
            cf:SetAlpha(1)
            if cf.editBox and cf.editBox.SetAlpha then
                ours = true
                cf.editBox:SetAlpha(EditBoxAlpha(cf.editBox))
                ours = false
            end
        end
    end
    if GENERAL_CHAT_DOCK then GENERAL_CHAT_DOCK:SetAlpha(1) end
    wipe(hiddenFor)
end

--- Was the companion reading the chat at login or the last /reload (Companion.lua)?
function F.Voiced()
    return ns.Companion.State() == "running"
end

--- Start or stop fading as the setting (and the addon's main switch) says - and the companion.
function F.Apply()
    if not driver then return end
    if ns.db.fadeChat and ns.db.enabled and F.Voiced() then
        driver:SetScript("OnUpdate", F.Update)
    else
        driver:SetScript("OnUpdate", nil)
        ShowAll()
    end
end

function F.Initialize()
    driver = CreateFrame("Frame")
    for _, name in ipairs(CHAT_FRAMES or {}) do Hook(_G[name]) end
    F.Apply()
end
