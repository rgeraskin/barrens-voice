-- The quest voice-overs and the chat (see below). Loaded before Core.lua, which hands its chat lines to
-- ns.Deliver; ns.Diag and ns.LineOptions (Core.lua) are called only at run time, not at load.
local _, ns = ...

-- The quest voice-over addons (CatQuest, Wayfarer) and the chat must not talk over each other: while
-- one reads a quest - a quest the player asked for - chat lines wait here and go to the strip once it
-- is done (the client cannot pause a sound and resume it in the middle, so pausing the quest would
-- restart it after every chat line). A line older than HOLD_MAX by then is dropped: stale chat.
-- Neither has an official interface for this; their globals are read with care, so that a version
-- without the fields simply counts as silent:
--  * CatQuest: CatQuestCore.state.playing / .pending - it speaks or is about to;
--  * Wayfarer (WayfarerRU since 1.2.0; the folder and global were "Wayfarer" before): WayfarerRU.Queue,
--    items[1] the one playing (.handle, .startedAt, .sound.duration) or about to (.waiting: after the
--    NPC's greeting); .paused - the player paused it. Its radio stories (items with .radio) too: the
--    player listens to them, the chat must not talk over them (the player asked, 2026-11-15).
--    Creature barks play outside the queue - a few words, not waited for.
local HOLD_MAX = 40
local held, holdTicker = {}, nil

local function CatQuestSpeaking()
    local core = rawget(_G, "CatQuestCore")
    local st = type(core) == "table" and type(core.state) == "table" and core.state
    if not st then return false end
    if st.playing == true then
        -- a track it says plays far past its own length: its "playing" is stuck (CatQuest's own
        -- comments warn of that) - do not hold the chat for it
        local started, length = tonumber(st.startedAt), tonumber(st.duration)
        return not (started and length and length > 0 and GetTime() > started + length + 3)
    end
    return st.pending ~= nil
end

local function WayfarerSpeaking()
    local wf = rawget(_G, "WayfarerRU")
    local q = type(wf) == "table" and type(wf.Queue) == "table" and wf.Queue
    if not q or q.paused == true or type(q.items) ~= "table" then return false end
    local item = q.items[1]
    if type(item) ~= "table" then return false end
    if item.waiting == true then return true end
    if item.handle == nil then return false end
    -- past its length and a bit: stuck, as with CatQuest
    local started = tonumber(item.startedAt)
    local length = type(item.sound) == "table" and tonumber(item.sound.duration)
    return not (started and length and length > 0 and GetTime() > started + length + 3)
end

-- NPC lines in the world (a city's herald, a mob's cry): the server sends only their text, and CatQuest's «Голоса
-- мира» and Wayfarer's barks voice them, each in a queue of its own, outside the quests' (the player, 2026-11-19:
-- Thrall's «Чествуйте своих героев» over a chat line was a mess). They are short: the chat waits for them as for a
-- quest, under the same setting.
--  * CatQuest: CatQuestCore.WorldQueue.Current(now) - the line playing (its .ends), nil when none;
--  * Wayfarer: Barks:Play knows the sound's length but keeps it to itself - a hook on it notes the start, and
--    Barks.recent (an entry of that very time, "played" or "chatty") tells that it did play (a file that would not
--    play is "failed"); Barks:Stop (a quest begins) ends it. Hooked once WayfarerRU.Barks is there (it loads after).
local function CatQuestWorldSpeaking()
    local core = rawget(_G, "CatQuestCore")
    local wq = type(core) == "table" and type(core.WorldQueue) == "table" and core.WorldQueue
    if not (wq and type(wq.Current) == "function") then return false end
    local ok, cur = pcall(wq.Current, GetTime())
    return ok and type(cur) == "table" and cur or false
end

local barkStart, barkLength, barkHooked
local function WayfarerBarks()
    local wf = rawget(_G, "WayfarerRU")
    local barks = type(wf) == "table" and type(wf.Barks) == "table" and wf.Barks
    if barks and not barkHooked and hooksecurefunc and type(barks.Play) == "function"
            and type(barks.Stop) == "function" then
        barkHooked = true
        hooksecurefunc(barks, "Play", function(_, sound)
            barkStart = GetTime()
            barkLength = type(sound) == "table" and tonumber(sound.duration) or 2
        end)
        hooksecurefunc(barks, "Stop", function() barkStart = nil end)
    end
    return barks
end

--- The length of the Wayfarer bark playing now, or nil.
local function WayfarerBarkSpeaking()
    local barks = WayfarerBarks()
    if not (barks and barkStart) then return nil end
    if GetTime() > barkStart + barkLength then barkStart = nil return nil end
    for _, entry in ipairs(type(barks.recent) == "table" and barks.recent or {}) do
        if type(entry) == "table" and entry.t == barkStart then
            return (entry.outcome == "played" or entry.outcome == "chatty") and barkLength or nil
        end
    end
    return nil
end

--- Whether CatQuest or Wayfarer speaks (or is about to): a quest, a story, an NPC's line. The chat waits.
local function QuestVoiceSpeaking()
    return CatQuestSpeaking() or WayfarerSpeaking() or CatQuestWorldSpeaking() ~= false
        or WayfarerBarkSpeaking() ~= nil
end

--- Send the waiting chat lines once CatQuest is silent; drop those that waited too long.
function ns.ReleaseHeld()
    if QuestVoiceSpeaking() and ns.db.waitForCatQuest ~= false then
        local now, kept = GetTime(), {}
        for _, h in ipairs(held) do
            if now - h.at <= HOLD_MAX then kept[#kept + 1] = h end
        end
        if #kept < #held then
            ns.Diag(("пропущено строк: %d — ждали озвучку CatQuest/Wayfarer дольше %d с"):format(#held - #kept, HOLD_MAX))
        end
        held = kept
        return
    end
    local now, dropped = GetTime(), 0
    for _, h in ipairs(held) do
        if now - h.at <= HOLD_MAX then
            ns.Strip.Push(h.payload)
            if ns.ChatFade then ns.ChatFade.Released(h.payload, h.at) end   -- its window again, for its reading
        else
            dropped = dropped + 1
        end
    end
    held = {}
    if dropped > 0 then ns.Diag(("пропущено строк: %d — ждали озвучку CatQuest/Wayfarer дольше %d с"):format(dropped, HOLD_MAX)) end
    if holdTicker then holdTicker:Cancel(); holdTicker = nil end
end

local voiceSeen
--- The quest voice-overs' state as the debug log tells it ("" when they are silent). Whether the chat waits is
--- the setting's too: with «Ждать озвучку CatQuest/Wayfarer» off it never does (ns.Deliver, ns.WatchCatQuest).
local function QuestVoiceState()
    local parts = {}
    local waits = ns.db.waitForCatQuest ~= false and " — чат ждёт"
        or " — чат не ждёт: «Ждать озвучку CatQuest/Wayfarer» снята"
    local core = rawget(_G, "CatQuestCore")
    local st = type(core) == "table" and type(core.state) == "table" and core.state
    if st and (st.playing == true or st.pending ~= nil) then
        local what = st.playing == true and ("CatQuest играет: %s, %s с"):format(tostring(st.source),
            tostring(st.duration and math.floor(st.duration + 0.5))) or "CatQuest ждёт своей очереди (pending)"
        parts[#parts + 1] = what .. (CatQuestSpeaking() and waits or " — считаем зависшим, чат не ждёт")
    end
    local wf = rawget(_G, "WayfarerRU")
    local q = type(wf) == "table" and type(wf.Queue) == "table" and wf.Queue
    local item = q and type(q.items) == "table" and q.items[1]
    if type(item) == "table" and (item.handle ~= nil or item.waiting == true) then
        local length = type(item.sound) == "table" and tonumber(item.sound.duration)
        local what = item.waiting == true and "Wayfarer ждёт конца приветствия NPC"
            or ("Wayfarer играет: %s, %s с"):format(item.questID and ("квест " .. tostring(item.questID))
                or item.radio ~= nil and "путевая история" or item.zone ~= nil and "лор места" or "реплика",
                tostring(length and math.floor(length + 0.5)))
        parts[#parts + 1] = what .. (WayfarerSpeaking() and waits
            or (q.paused == true and " — на паузе, чат не ждёт") or " — считаем зависшим, чат не ждёт")
    end
    local cur = CatQuestWorldSpeaking()
    if cur then
        parts[#parts + 1] = ("CatQuest: голос мира, ещё %s с"):format(
            tostring(tonumber(cur.ends) and math.max(0, math.floor(cur.ends - GetTime() + 0.5)))) .. waits
    end
    local bark = WayfarerBarkSpeaking()
    if bark then
        parts[#parts + 1] = ("Wayfarer: фраза NPC, %d с"):format(math.floor(bark + 0.5)) .. waits
    end
    return table.concat(parts, "; ")
end

-- While a quest voice-over (or an NPC's line) speaks the program pauses: the chat line being read is cut and said again
-- from its start once it is silent, then the queue goes on. nil at first: the first check tells the
-- program the state either way (a /reload during a pause must not leave it paused).
local pausedForCatQuest

--- Every 0.25 s: pause or resume the program with the quest voice-overs' speech; the debug notes.
function ns.WatchCatQuest()
    local speaking = ns.db.enabled and ns.db.waitForCatQuest ~= false and QuestVoiceSpeaking() or false
    if speaking ~= pausedForCatQuest then
        pausedForCatQuest = speaking
        ns.Strip.PushFirst(ns.ServiceFrame(speaking and "pause" or "resume", ns.LineOptions(), "-"))
    end
    if not ns.db.debug then voiceSeen = nil; return end
    local now = QuestVoiceState()
    if now ~= voiceSeen then
        if voiceSeen ~= nil or now ~= "" then ns.Diag(now == "" and "CatQuest и Wayfarer замолчали" or now) end
        voiceSeen = now
    end
end

--- Forget the lines waiting for a quest voice-over (/bv off: they must not be read at the next /bv on).
function ns.DropHeld()
    held = {}
    if holdTicker then holdTicker:Cancel(); holdTicker = nil end
end

--- A chat line to the strip - now, or after the quest voice-over has finished speaking. None while
--- the addon is off: the strip takes nothing then, and a held line would wait for the next /bv on.
function ns.Deliver(payload)
    if not ns.db.enabled then return end
    if ns.db.waitForCatQuest == false or (#held == 0 and not QuestVoiceSpeaking()) then
        ns.Strip.Push(payload)
        return
    end
    held[#held + 1] = { payload = payload, at = GetTime() }
    if ns.db.debug then ns.Diag(("строка ждёт озвучку CatQuest/Wayfarer (в очереди %d)"):format(#held)) end
    if not holdTicker and C_Timer and C_Timer.NewTicker then
        holdTicker = C_Timer.NewTicker(0.25, ns.ReleaseHeld)
    end
end
