-- «Что нового»: what each release of Barrens Voice brought, for players (Russian, «ты»; CHANGELOG.md is the
-- developers' English). The entries come from the companion: at its start it writes those of its own version from
-- the release's news.toml into NewsData.lua (BarrensVoiceNewsData, loaded before this file), together with that
-- version - the program's, which every release raises (the addon's own moves only when the addon changed), so what
-- is compared and kept as seen here is the program's version. Before the companion first runs there is nothing.
-- After an update, a few seconds after login and never in combat, the entries the player has not seen are shown
-- once: with a "big" one among them (a feature, something that works differently) the window, else ("small": fixes,
-- dictionary words) one chat line with the newest one's summary. Seen is kept per entry (`newsSeen` in the saved
-- variables, by the entry's version), so the first run marks everything seen: a newcomer gets the welcome instead.
--
-- An entry belongs to a release ("0.4.0"); a test build ("0.4.0b5") shows its release's entry, once, as soon as it
-- is written. An entry of a test build's own (version = "0.4.0b6") is shown from that build on: the way to tell the
-- testers who saw the release's entry already what a later build brought.
local _, ns = ...

local N = {}
ns.News = N

N.DELAY = 5            -- seconds after login: after the companion's word (Companion.lua), the chat settled
N.AFTER_COMBAT = 2     -- seconds after the combat ends: a pull right after another waits again

--- A version's parts: "0.4.0" -> { 0, 4, 0, huge }, "0.4.0b5" -> { 0, 4, 0, 5 } (a test build is older than its
--- release); nil for anything else (nil: the companion has written nothing yet).
local function Parts(v)
    if type(v) ~= "string" then return nil end
    local a, b, c = v:match("^(%d+)%.(%d+)%.(%d+)$")
    if a then return { tonumber(a), tonumber(b), tonumber(c), math.huge } end
    local beta
    a, b, c, beta = v:match("^(%d+)%.(%d+)%.(%d+)b(%d+)$")
    if a then return { tonumber(a), tonumber(b), tonumber(c), tonumber(beta) } end
    return nil
end

--- -1, 0 or 1: "0.4.0b5" < "0.4.0" < "0.4.1"; nil when either is not a version.
function N.Compare(a, b)
    a, b = Parts(a), Parts(b)
    if not (a and b) then return nil end
    for i = 1, 4 do
        if a[i] ~= b[i] then return a[i] < b[i] and -1 or 1 end
    end
    return 0
end

--- The release a version leads to: "0.4.0b5" -> "0.4.0".
function N.Release(version) return (version:gsub("b%d+$", "")) end

--- For people: "0.4.0b5" -> "0.4.0 beta 5" (the launcher's install.display_version).
function N.Shown(version) return (version:gsub("b(%d+)$", " beta %1")) end

--- What the companion wrote (NewsData.lua), or nil: { version = the program's, entries = { ... } }.
local function Data()
    local data = rawget(_G, "BarrensVoiceNewsData")
    return type(data) == "table" and data or nil
end

--- The installed version the news are of - the program's, as the companion wrote it ("0.4.0b16"); nil before the
--- companion first ran.
function N.Installed()
    local data = Data()
    return data and Parts(data.version) and data.version or nil
end

--- The companion's entries, each { version, date (none until released), kind, title, summary, items }; one it
--- could not have meant (no version, title, summary or items) is left out.
function N.Entries()
    local data = Data()
    local out = {}
    for _, e in ipairs(data and type(data.entries) == "table" and data.entries or {}) do
        if type(e) == "table" and Parts(e.version) and type(e.title) == "string" and type(e.summary) == "string"
                and type(e.items) == "table" then
            out[#out + 1] = e
        end
    end
    return out
end

--- The entries the installed version has, newest first: a release's from its first test build on, a test build's
--- own from that build on. None when the version is not known.
function N.Visible(installed)
    if not Parts(installed) then return {} end
    local release = N.Release(installed)
    local out = {}
    for _, e in ipairs(N.Entries()) do
        local beta = e.version:find("b%d+$")
        local order = N.Compare(e.version, beta and installed or release)
        if order and order <= 0 then out[#out + 1] = e end
    end
    table.sort(out, function(a, b) return N.Compare(a.version, b.version) > 0 end)
    return out
end

--- Set up the seen entries once (before the version last seen moves on): the first run sees everything; an addon
--- from before this list (only `seenVersion`) has seen what is not newer than that version - so a test build's
--- player sees the release's entry once. Until the companion has written the news it waits (a first run is kept
--- as `newsFresh`): a newcomer whose first login came before the companion still gets no history.
function N.Prepare(installed, firstRun)
    local db = ns.db
    if type(db.newsSeen) == "table" then return end
    if not Parts(installed) then
        if firstRun then db.newsFresh = true end
        return
    end
    firstRun = firstRun or db.newsFresh
    db.newsFresh = nil
    db.newsSeen = {}
    for _, e in ipairs(N.Visible(installed)) do
        local order = N.Compare(e.version, db.seenVersion)
        if firstRun or (order and order <= 0) then db.newsSeen[e.version] = true end
    end
end

--- The entries the installed version has that the player has not seen, newest first.
function N.Unseen(installed)
    local seen = type(ns.db.newsSeen) == "table" and ns.db.newsSeen or {}
    local out = {}
    for _, e in ipairs(N.Visible(installed)) do
        if not seen[e.version] then out[#out + 1] = e end
    end
    return out
end

-- The chat line's [Что нового]: a link of the clients' own "addon" type (LinkTypes.AddOn, LinkUtil.lua). A click
-- in a chat window goes ChatFrameMixin:OnHyperlinkClick -> SetItemRef -> LinkUtil.ProcessLink, whose handler for
-- the type (ItemRefHandlersShared.lua) only fires EventRegistry's "SetItemRef" and counts the link handled: no
-- ItemRefTooltip, and with Shift nothing goes into the edit box (SetItemRef's modified-click branch comes after).
-- EventRegistry calls each callback through securecallfunction, so the game's code is not tainted; ours only opens
-- our window. The same code in the forever and live branches of the UI source.
N.LINK = "addon:BarrensVoice:news"
local LINK_COLOR = "|cffffd100"

--- EventRegistry's "SetItemRef": our link opens the window, any other addon's link is left alone.
function N.OnLink(_, link)
    if ns.Secret(link) or link ~= N.LINK then return end
    if ns.NewsWindow then ns.NewsWindow.Show() end
end

do
    local registry, types = rawget(_G, "EventRegistry"), rawget(_G, "LinkTypes")
    if type(registry) == "table" and type(registry.RegisterCallback) == "function" and type(types) == "table"
            and types.AddOn == "addon" then
        N.linked = pcall(registry.RegisterCallback, registry, "SetItemRef", N.OnLink, N)
    end
end

--- Where the whole of it is, at the end of the chat line: the link, or the command where a click would go nowhere.
function N.More()
    if not N.linked then return "Что нового — /bv news." end
    return LINK_COLOR .. "|H" .. N.LINK .. "|h[Что нового]|h|r"
end

--- The chat line for an update: the addon's icon, «Barrens Voice:», the version and the newest entry's summary,
--- then where to read the rest (the «Что нового» window).
function N.ChatLine(entry, installed)
    return ns.ICON .. " " .. ns.PREFIX .. ("обновление %s — %s. %s"):format(N.Shown(installed), entry.summary, N.More())
end

--- What the player has not seen, shown now and marked seen: the window for a big entry (unless the setting
--- «Окно «Что нового» после обновлений» is off), else the chat line.
function N.Show(installed)
    local unseen = N.Unseen(installed)
    if #unseen == 0 then return end
    if type(ns.db.newsSeen) ~= "table" then ns.db.newsSeen = {} end
    local big = false
    for _, e in ipairs(unseen) do
        ns.db.newsSeen[e.version] = true
        if e.kind == "big" then big = true end
    end
    if big and ns.db.newsWindow ~= false and ns.NewsWindow then
        ns.NewsWindow.Show()
    else
        print(N.ChatLine(unseen[1], installed))
    end
end

local waiter   -- the frame that waits for the combat to end

--- Show the news now, or once out of combat (PLAYER_REGEN_ENABLED, then N.AFTER_COMBAT seconds, and again if a
--- new pull started meanwhile).
function N.Check(installed)
    if InCombatLockdown and InCombatLockdown() then
        waiter = waiter or CreateFrame("Frame")
        waiter:RegisterEvent("PLAYER_REGEN_ENABLED")
        waiter:SetScript("OnEvent", function(self)
            self:UnregisterEvent("PLAYER_REGEN_ENABLED")
            if C_Timer then C_Timer.After(N.AFTER_COMBAT, function() N.Check(installed) end) else N.Check(installed) end
        end)
        return
    end
    N.Show(installed)
end

--- After login (and /reload): the check, N.DELAY seconds later.
function N.AtLogin(installed)
    if C_Timer then C_Timer.After(N.DELAY, function() N.Check(installed) end) else N.Check(installed) end
end
