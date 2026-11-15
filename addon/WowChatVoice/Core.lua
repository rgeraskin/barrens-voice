-- Chat events -> payload for the strip: kind, sender, race, sex, class, channel, options, text,
-- joined by the unit separator (\31); options are "key=value;..." (rate, voice). The companion
-- picks a voice by sender, race and sex.
local ADDON, ns = ...

ns.DEFAULTS = {
    enabled = true,
    party = true,      -- party and party leader
    raid = true,       -- raid and raid leader
    warning = true,    -- raid warnings
    instance = true,   -- instance chat (dungeon finder groups, battlegrounds)
    say = true,
    yell = true,
    whisper = true,    -- whispers to you
    guild = true,
    officer = false,
    channels = false,  -- numbered channels: General, Trade, LookingForGroup, LocalDefense ...
    chGeneral = true,  -- ... which of them once "channels" is on: General,
    chTrade = true,    --     Trade,
    chLfg = true,      --     LookingForGroup,
    chDefense = true,  --     LocalDefense / WorldDefense,
    chOther = true,    --     any other numbered channel (a custom one)
    emote = false,     -- /e emotes
    fadeChat = false,  -- chat windows transparent until the mouse is over them (ChatFade.lua)
    fadeWhisper = false, -- ... but a whisper shows the window though it is read aloud
    fadeGuild = false, --     and so does a guild (or officer) line
    skipAddons = true, -- lines other players' addons write for them (Questie, DBM...) are not read
    debug = false,     -- /wcv debug: why a chat line was not sent, and CatQuest's speech, to the program's log
    self = false,      -- your own lines
    onlyVisible = true, -- only lines a chat window of yours shows (its message types and channels, chat filters)
    waitForCatQuest = true, -- hold chat lines while CatQuest or Wayfarer reads a quest; send them when it is done
    cell = 2,          -- strip cell size, physical pixels
    rows = 1,          -- strip rows of cells
    -- the strip's cells start at the "left" edge of it or the "right"
    stripFrom = "left",
    -- where the strip is: "top" (default), "bottom" or "custom" (stripX, stripY, stripWidth: physical
    -- pixels of its top left corner and its width) - for another addon drawing in the same place
    stripPlace = "top",
    stripX = 0,
    stripY = 0,
    stripWidth = 800,
    -- dictionaryEdits: the player's changes to the default slang dictionary (Dictionary.lua, layers)
    rate = 100,        -- reading speed, percent of the voice's own pace (50..200)
    volume = 100,      -- loudness, percent (0..200: over 100 the program boosts, easing the peaks), on top of the program's own `volume`
    minimapIcon = true,
    minimapAngle = 160, -- degrees on the minimap ring (CatQuest's sits at 200)
    sayNames = false,  -- "Name: text"
    sayVerb = false,   -- "Name says: text" (says / yells / whispers / writes, by chat kind)
    sayLastNames = false, -- the whole name ("Ивар Седой"); off: up to the first space ("Ивар")
    declension = true, -- the program declines dictionary replacements after prepositions (pymorphy3)
    voices = "f5",     -- "f5": race voices (CatQuest, F5-TTS); "sapi": Windows voices
    -- voiceOff: [Windows voice name] = true for voices switched off; nil until changed here (the
    -- program then uses its own defaults)
}

-- Event -> setting that switches it on.
local EVENTS = {
    CHAT_MSG_PARTY = "party",
    CHAT_MSG_PARTY_LEADER = "party",
    CHAT_MSG_RAID = "raid",
    CHAT_MSG_RAID_LEADER = "raid",
    CHAT_MSG_RAID_WARNING = "warning",
    CHAT_MSG_INSTANCE_CHAT = "instance",
    CHAT_MSG_INSTANCE_CHAT_LEADER = "instance",
    CHAT_MSG_SAY = "say",
    CHAT_MSG_YELL = "yell",
    CHAT_MSG_WHISPER = "whisper",
    CHAT_MSG_GUILD = "guild",
    CHAT_MSG_OFFICER = "officer",
    CHAT_MSG_CHANNEL = "channels",
    CHAT_MSG_EMOTE = "emote",
}

local SEP = "\31"
local VERBS = { say = "говорит", yell = "кричит", whisper = "шепчет", test = "говорит" }
local PREFIX = "|cff66ccffWoW Chat Voice|r: "

--- A line that is nothing but a question or questions ("кто в ОП?", "танк нужен? хил?"): no full stop,
--- exclamation mark or ellipsis anywhere, and it ends with "?". The voices rise at a question mark
--- unevenly, so such a line is announced "спрашивает" - the ear gets it from the verb.
function ns.IsQuestion(text)
    return type(text) == "string" and text:find("%?%s*$") ~= nil and not text:find("[%.!…]")
end

--- Chat text without the client's markup: colours, links (their visible text kept), textures,
--- atlases and raid target icons ({rt1}, {череп}).
function ns.Clean(text)
    -- colours: "|cffRRGGBB", or by name: "|cnIQ1:" (an item quality's colour, in newer clients' links)
    text = text:gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|cn[%w_]-:", ""):gsub("|r", "")
    text = text:gsub("|H.-|h%[?(.-)%]?|h", " %1 ")     -- a quest or item link: its name, without the brackets
                                                        -- (spaced: two links in a row stay two names)
    text = text:gsub("|T.-|t", ""):gsub("|A.-|a", "")
    text = text:gsub("{.-}", ""):gsub("||", "|")
    -- A "+" typed in chat is the word; every "+" after this point is a dictionary stress mark.
    text = text:gsub("%+", " плюс ")
    text = text:gsub(SEP, " "):gsub("%s+", " ")
    text = ns.Emoticons(text):gsub("%s+([%?!,%.])", "%1")
    return (text:gsub("^ ", ""):gsub(" $", ""))
end

--- Brackets used for feelings, not as brackets, read as a full stop: ")" "))" "(((" ":)" ":D" ";P".
--- A bracket with its pair in the line stays: "(через 5 мин)".
function ns.Emoticons(text)
    -- ")(" "}{" "><" next to letters is an "х" in disguise (past the swear filter): "на)(уя"
    text = text:gsub("([\128-\191])[%)}>][%({<]([\208\209])", "%1х%2")
    text = text:gsub("^[%)}>][%({<]([\208\209])", "х%1"):gsub("(%s)[%)}>][%({<]([\208\209])", "%1х%2")
    -- :) :( :D ;) :-P :Р (Р - Russian). Lua patterns see bytes: a Russian letter in a [set] would be
    -- two loose bytes there and eat the first byte of any letter after a colon ("1:Сильный"), so it
    -- goes as a sequence; a letter smiley only when no letter follows it ("ссылка:Dota" stays).
    text = text:gsub("[:;=]%-?[%)%(]+", ".")
    text = text:gsub("[:;=]%-?[DdPp]+%f[^%w\128-\255]", ".")
    text = text:gsub("[:;=]%-?\208\160%f[^%w\128-\255]", "."):gsub("[:;=]%-?\209\128%f[^%w\128-\255]", ".")
    text = text:gsub("[%(%)][%(%)]+", ".")                  -- )) ((( )(
    local opens = select(2, text:gsub("%(", ""))
    local closes = select(2, text:gsub("%)", ""))
    if opens ~= closes then
        text = text:gsub("[%(%)]", ".")                     -- a lone bracket: "привет)"
    end
    text = text:gsub("%s+%.", "."):gsub("%.%.+", "."):gsub("([!?])%.", "%1"):gsub("%.%s*([!?])", "%1")
    return text
end

-- The name before a line is followed by a mark (\4): the program drops it when the same character
-- goes on while their previous line is still being said or was just said (it knows when a line
-- ends; the addon does not) - several lines in a row heard as one speech. After an emote's name the
-- mark is \5: never dropped. Either way the program applies the dictionary to the line alone, not
-- to the name ("Лок" stays a name).
local NAME_MARK, KEPT_NAME_MARK = "\4", "\5"

local SESSION = ("%x%02x"):format((time and time() or 0) % 0x100000, math.random(0, 255))
local lineCount = 0

function ns.Send(kind, sender, race, sex, class, channel, text)
    local raw = (text or ""):gsub(SEP, " ")
    text = ns.Clean(text or "")          -- the dictionary is the program's (it reads Dictionary.lua itself)
    text = text:gsub("%s+", " "):gsub("^ ", ""):gsub(" $", "")
    if text == "" then ns.Skip("пусто после очистки разметки", sender, raw) return end
    if ns.db.sayNames and sender and sender ~= "" then
        local name = Ambiguate and Ambiguate(sender, "none") or sender:match("^[^-]+")
        if not ns.db.sayLastNames then name = name:match("^%S+") or name end
        if kind == "emote" then
            text = name .. KEPT_NAME_MARK .. " " .. text   -- "Вася смеётся"
        elseif ns.db.sayVerb then
            local verb = VERBS[kind] or "пишет"
            if kind ~= "yell" and kind ~= "whisper" and ns.IsQuestion(text) then verb = "спрашивает" end
            text = name .. " " .. verb .. ":" .. NAME_MARK .. " " .. text
        else
            text = name .. ":" .. NAME_MARK .. " " .. text
        end
    end
    lineCount = lineCount + 1
    -- an id the companion knows a line by: a line sent again is read once; the session tag keeps ids
    -- apart across /reload
    local options = ns.LineOptions() .. (";decl=%d;id=%s-%d;raw=1"):format(ns.db.declension == false and 0 or 1,
        SESSION, lineCount) .. (ns.replaying and ";replay=1" or "")
    -- the line as typed goes last, for the program's log: when the strip is short of room, it is
    -- what gets cut, not the text to say
    local payload = table.concat({ kind, sender or "", race or "", tostring(sex or ""), class or "",
        channel or "", options, text, raw }, SEP)
    ns.Deliver(payload)
end

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

--- Whether a quest voice-over speaks (or is about to): the chat waits.
local function QuestVoiceSpeaking()
    return CatQuestSpeaking() or WayfarerSpeaking()
end

--- Send the waiting chat lines once CatQuest is silent; drop those that waited too long.
function ns.ReleaseHeld()
    if QuestVoiceSpeaking() and ns.db.waitForCatQuest ~= false then
        local now, kept = GetTime(), {}
        for _, h in ipairs(held) do
            if now - h.at <= HOLD_MAX then kept[#kept + 1] = h end
        end
        if #kept < #held then
            ns.Diag(("пропущено строк: %d — ждали озвучку квеста дольше %d с"):format(#held - #kept, HOLD_MAX))
        end
        held = kept
        return
    end
    local now, dropped = GetTime(), 0
    for _, h in ipairs(held) do
        if now - h.at <= HOLD_MAX then ns.Strip.Push(h.payload) else dropped = dropped + 1 end
    end
    held = {}
    if dropped > 0 then ns.Diag(("пропущено строк: %d — ждали озвучку квеста дольше %d с"):format(dropped, HOLD_MAX)) end
    if holdTicker then holdTicker:Cancel(); holdTicker = nil end
end

--- A note for the program's log (kind "diag": logged, never spoken) - what the addon dropped.
function ns.Diag(text)
    ns.Strip.Push(table.concat({ "diag", "", "", "", "", "", ns.LineOptions(), text }, SEP))
end

-- Debug (/wcv debug): each chat line the addon gets but does not send, with the reason, and when
-- CatQuest or Wayfarer starts and stops speaking - notes in the program's log, which has the time the chat lacks.
function ns.Skip(reason, sender, text)
    if not ns.db.debug then return end
    local who = sender and sender:match("^[^-]+") or sender or "?"
    text = (text or ""):gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", ""):gsub("|H.-|h(.-)|h", "%1")
    ns.Diag(("не отправлено (%s): %s: %s"):format(reason, who, ns.Protocol.TrimUTF8(text, 90)))
end

local voiceSeen
--- The quest voice-overs' state as the debug log tells it ("" when they are silent).
local function QuestVoiceState()
    local parts = {}
    local core = rawget(_G, "CatQuestCore")
    local st = type(core) == "table" and type(core.state) == "table" and core.state
    if st and (st.playing == true or st.pending ~= nil) then
        local what = st.playing == true and ("CatQuest играет: %s, %s с"):format(tostring(st.source),
            tostring(st.duration and math.floor(st.duration + 0.5))) or "CatQuest ждёт своей очереди (pending)"
        parts[#parts + 1] = what .. (CatQuestSpeaking() and " — чат ждёт" or " — считаем зависшим, чат не ждёт")
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
        parts[#parts + 1] = what .. (WayfarerSpeaking() and " — чат ждёт"
            or (q.paused == true and " — на паузе, чат не ждёт") or " — считаем зависшим, чат не ждёт")
    end
    return table.concat(parts, "; ")
end

-- While a quest voice-over speaks the program pauses: the chat line being read is cut and said again
-- from its start once it is silent, then the queue goes on. nil at first: the first check tells the
-- program the state either way (a /reload during a pause must not leave it paused).
local pausedForCatQuest

--- Every 0.25 s: pause or resume the program with the quest voice-overs' speech; the debug notes.
function ns.WatchCatQuest()
    local speaking = ns.db.enabled and ns.db.waitForCatQuest ~= false and QuestVoiceSpeaking() or false
    if speaking ~= pausedForCatQuest then
        pausedForCatQuest = speaking
        ns.Strip.PushFirst(table.concat({ speaking and "pause" or "resume", "", "", "", "", "", ns.LineOptions(), "-" }, SEP))
    end
    if not ns.db.debug then voiceSeen = nil; return end
    local now = QuestVoiceState()
    if now ~= voiceSeen then
        if voiceSeen ~= nil or now ~= "" then ns.Diag(now == "" and "озвучка квестов замолчала" or now) end
        voiceSeen = now
    end
end

--- A chat line to the strip - now, or after the quest voice-over has finished speaking.
function ns.Deliver(payload)
    if ns.db.waitForCatQuest == false or (#held == 0 and not QuestVoiceSpeaking()) then
        ns.Strip.Push(payload)
        return
    end
    held[#held + 1] = { payload = payload, at = GetTime() }
    if ns.db.debug then ns.Diag(("строка ждёт озвучку квеста (в очереди %d)"):format(#held)) end
    if not holdTicker and C_Timer and C_Timer.NewTicker then
        holdTicker = C_Timer.NewTicker(0.25, ns.ReleaseHeld)
    end
end

--- The options every line carries: speed, loudness and engine ("f5" or "sapi"; `voice` overrides).
-- What the sliders call 100 % is not the program's 100 %: the voices are slow and quiet at the program's
-- own 100, so the sliders' 100 stands for RATE_BASE and VOLUME_BASE of it (125 % speed, 120 % volume,
-- as the author's own settings were). The program takes 50..200 of the speed and 0..240 of the volume; the
-- sliders run 40..160 and 0..200, so the thumbs of the two stand alike at 100 (the middle).
ns.RATE_BASE, ns.VOLUME_BASE = 1.25, 1.2

--- What the slider's value means to the program.
function ns.Effective(value, base)
    return math.floor((value or 100) * base + 0.5)
end

--- A saved setting from before the sliders' 100 stood for a base (the program's own scale): the same
--- sound as before, on the new scale, to the step of 5.
function ns.MigrateScale(db)
    if db.scale == 1 then return end
    local function convert(v, base, hi)
        return math.max(0, math.min(hi, math.floor((v / base) / 5 + 0.5) * 5))
    end
    if type(db.rate) == "number" then db.rate = math.max(40, convert(db.rate, ns.RATE_BASE, 160)) end
    if type(db.volume) == "number" then db.volume = convert(db.volume, ns.VOLUME_BASE, 200) end
    db.scale = 1
end

function ns.LineOptions(voice)
    return ("rate=%d;vol=%d;voice=%s"):format(ns.Effective(ns.db.rate, ns.RATE_BASE),
        ns.Effective(ns.db.volume, ns.VOLUME_BASE), voice or ns.db.voices or "f5")
end

--- A line the companion does not speak: the current settings (which voices to keep loaded, which
--- Windows voices are off).
--- The settings frame: options, the Windows voices switched off, and where the strip is
--- (strip=x,y,width,height,screen width,screen height, physical pixels).
function ns.ControlPayload()
    local options = ns.LineOptions() .. ";strip=" .. ns.Strip.Describe()
    if ns.db.voiceOff then
        local off = {}
        for name in pairs(ns.db.voiceOff) do off[#off + 1] = name end
        table.sort(off)
        options = options .. ";off=" .. table.concat(off, "|")
    end
    return table.concat({ "control", "", "", "", "", "", options, "-" }, SEP)
end

function ns.SendControl()
    ns.Strip.Push(ns.ControlPayload())
end

-- The player's dictionary layer (their edits of the default: Dictionary.D.UserLayer) goes to the
-- program over the strip, in parts of at most DICT_PART bytes (cut at line ends), tagged with a
-- checksum of the whole layer: "id=..;part=i;of=n". Sent when it changes (2 s after the last edit),
-- at login, and every 2 minutes when it changed in this session (else a program started after the
-- game reads the same layer from the saved variables, which the game writes on /reload and logout).
-- The default itself the program reads from Dictionary.lua.
local DICT_PART = 480
local lastLayer

--- The layer as sent and its id (CRC-16, hex).
local function LayerSet()
    local text = ns.Dictionary.UserLayer()
    local bytes = {}
    for i = 1, #text do bytes[i] = text:byte(i) end
    return text, ("%04x"):format(ns.Protocol.CRC16(bytes))
end

function ns.SendDictionary(force)
    local text, id = LayerSet()
    if not force and id == lastLayer then return end
    lastLayer = id
    local parts, current = {}, ""
    for line in (text .. "\n"):gmatch("(.-)\n") do
        line = ns.Protocol.TrimUTF8(line, DICT_PART)
        if current ~= "" and #current + 1 + #line > DICT_PART then
            parts[#parts + 1] = current
            current = line
        else
            current = current == "" and line or (current .. "\n" .. line)
        end
    end
    parts[#parts + 1] = current
    for i, part in ipairs(parts) do
        local options = ("id=%s;part=%d;of=%d"):format(id, i, #parts)
        ns.Strip.Push(table.concat({ "dict", "", "", "", "", "", options, part }, SEP))
    end
end

local layerTimer
function ns.DictionaryChanged()
    if not (C_Timer and ns.Strip and ns.db) then return end
    if layerTimer then layerTimer:Cancel() end
    layerTimer = C_Timer.NewTimer(2, function() layerTimer = nil; ns.SendDictionary(false) end)
end

-- Pages the companion opens in the browser on a click in the settings (an addon cannot: LaunchURL is
-- Blizzard's own). The addon sends only the name; the companion keeps its own list of the same
-- addresses (wcv/links.py) and opens nothing else.
ns.LINKS = {
    rhvoice = { "RHVoice", "https://rhvoice.su/voices/" },
    silero = { "Silero", "https://github.com/snakers4/silero-models/releases?q=SAPI" },
}

--- Ask the companion to open one of ns.LINKS in the browser; the address goes to the chat too.
function ns.OpenLink(key)
    local link = ns.LINKS[key]
    if not link then return end
    ns.Strip.Push(table.concat({ "open", "", "", "", "", "", ns.LineOptions(), key }, SEP))
    print(PREFIX .. ("%s: компаньон откроет страницу в браузере. Если не открылась (компаньон не запущен) — адрес: %s")
        :format(link[1], link[2]))
end

--- Ask the program to forget which race voice each character had and hand them out afresh.
function ns.ResetVoices()
    local options = ns.LineOptions()
    ns.Strip.Push(table.concat({ "reset", "", "", "", "", "", options, "-" }, SEP))
    print(PREFIX .. "голоса рас будут розданы заново: каждый персонаж получит голос, когда заговорит.")
end

--- A test line in one Windows voice (the voices window's play buttons).
function ns.TestVoice(name)
    local options = ns.LineOptions("sapi") .. ";sapi=" .. name
    ns.Strip.Push(table.concat({ "test", "Проверка", "", "", "", "", options,
        "Привет! Нужен дам+агер в Мёртвые копи, продам сумки за пять тысяч." }, SEP))
end


function ns.SetVoices(value)
    ns.db.voices = value
    ns.SendControl()
    if value == "f5" then
        print(PREFIX .. "голоса рас. Компаньон загружает модель — около 15 секунд, пока читают голоса Windows.")
    else
        print(PREFIX .. "голоса Windows. Компаньон выгружает модель голосов рас.")
    end
end

-- The last chat lines read, as they came (before the dictionary), for /wcv last N. Kept in the saved
-- variables (written at /reload and logout), so they outlive a /reload and a game restart - not a
-- crash. The saved variables are the account's: another character replays the same lines.
local HISTORY = 50
ns.history = {}

--- Take the history the saved variables kept (at load, once ns.db is there).
function ns.RestoreHistory()
    if type(ns.db.history) ~= "table" then ns.db.history = {} end
    ns.history = ns.db.history
    while #ns.history > HISTORY do table.remove(ns.history, 1) end
end

local function Remember(...)
    table.insert(ns.history, { n = select("#", ...), ... })   -- n: a nil (no race known) stays in place
    if #ns.history > HISTORY then table.remove(ns.history, 1) end
end

--- Read the last `n` chat lines again, through the current dictionary and settings.
function ns.Replay(n)
    n = math.max(1, math.min(n or 5, #ns.history))
    if #ns.history == 0 then
        print(PREFIX .. "пока нечего повторять: ни одной прочитанной строки чата.")
        return
    end
    -- marked replay=1: the companion drops none of them when its queue is full (live lines it may)
    ns.replaying = true
    for i = #ns.history - n + 1, #ns.history do
        local h = ns.history[i]
        ns.Send(unpack(h, 1, h.n))
    end
    ns.replaying = false
    print(PREFIX .. ("повторяю последние строки: %d."):format(n))
end

--- Whether chat window `frame` takes this kind of line: its message types (Chat settings), or for
--- a channel line its channels - matched the way the game's chat frame matches them (zone channel
--- id, else the channel's base name).
local function Takes(frame, event, zoneChannel, baseName)
    if event == "CHAT_MSG_CHANNEL" then
        for index, name in pairs(frame.channelList or {}) do
            if (zoneChannel and zoneChannel > 0 and frame.zoneChannelList
                    and frame.zoneChannelList[index] == zoneChannel)
                or (baseName and name and name:upper() == baseName:upper()) then
                return true
            end
        end
        return false
    end
    local group = (ChatTypeGroupInverted and ChatTypeGroupInverted[event]) or event:sub(10)
    for _, g in pairs(frame.messageTypeList or {}) do
        if g == group then return true end
    end
    return false
end

--- Whether the player sees this line: some chat window that is open (shown or docked as a tab)
--- takes it, and no chat filter - spam blockers and the like - hides it there.
local function Visible(event, ...)
    if not ns.db.onlyVisible or not GetChatWindowInfo then return true end
    local zoneChannel, baseName = select(7, ...), select(9, ...)
    local seen
    for i = 1, NUM_CHAT_WINDOWS or 10 do
        local frame = _G["ChatFrame" .. i]
        local shown, _, docked = select(7, GetChatWindowInfo(i))
        if frame and (shown or docked) and Takes(frame, event, zoneChannel, baseName) then
            seen = frame
            break
        end
    end
    if not seen then return false, "нет открытого окна чата с этим типом или каналом" end
    local filters = ChatFrame_GetMessageEventFilters and ChatFrame_GetMessageEventFilters(event)
    ns.askingFilters = true       -- our own chat filter (ChatFade.lua) keeps out of this
    for i, filter in ipairs(filters or {}) do
        local ok, hide = pcall(filter, seen, event, ...)
        if ok and hide then
            ns.askingFilters = false
            return false, ("скрыто фильтром чата другого аддона (№%d)"):format(i)
        end
    end
    ns.askingFilters = false
    return true
end

ns.EVENTS = EVENTS   -- the chat events the addon reads (ChatFade.lua marks their lines with a filter)

-- Addons that write into the chat for their player: party progress (Questie), boss timers (DBM,
-- BigWigs), meters (Details!, Skada, Recount), announcers (RSA)... A line is taken for one when it
-- starts with a raid target icon and a Latin word with a colon ("{звезда} Questie: ... 1/1"; players
-- who put an icon first go on in Russian), or with one of these names: "<DBM>", "[Questie]",
-- "Details!:". Lowercase, as the line is lowered to be matched.
ns.ADDON_TAGS = {}
-- (no names a character could have - "Nova: привет" is a player talking to Nova)
for _, name in ipairs({ "questie", "dbm", "bigwigs", "details", "skada", "recount", "rsa",
                        "novainstancetracker", "leatrix", "autoinvite", "elvui", "vuhdo", "healbot",
                        "weakauras", "mrt", "exrt", "angryassign", "raidassist", "questhelper", "guidelime",
                        "restedxp", "zygor", "lfgbulletinboard", "classicquestlog", "auctionator" }) do
    ns.ADDON_TAGS[name] = true
end

--- The addon a chat line comes from (its name as written), or nil for a line a player typed.
function ns.AddonLine(text)
    if type(text) ~= "string" then return nil end
    local name = text:match("^%s*{[^}]+}%s*(%a[%w%-]*!?)%s*:")
    if name then return name end
    name = text:match("^%s*[<%[]%s*(%a[%w%-]*!?)%s*[>%]]") or text:match("^%s*(%a[%w%-]*!?)%s*:")
    if name and ns.ADDON_TAGS[(name:gsub("!$", "")):lower()] then return name end
    return nil
end

-- The numbered channels the settings tell apart: setting, a piece of the channel's base name (as the
-- client sends it, Russian or English; "Общий" is cut to "бщий" and so on so a capital never matters).
ns.CHANNEL_KINDS = {
    { "chGeneral", "бщий", "general" },
    { "chTrade", "орговля", "trade" },
    { "chLfg", "оиск спутников", "lookingforgroup" },
    { "chDefense", "борона", "defense" },
}

--- The setting of the numbered channel a line came from (chOther for a channel not in the list).
function ns.ChannelSetting(baseName, channelString)
    local name = tostring(baseName or "")
    if name == "" then name = tostring(channelString or "") end
    local lower = name:lower()
    for _, k in ipairs(ns.CHANNEL_KINDS) do
        if name:find(k[2], 1, true) or lower:find(k[3], 1, true) then return k[1] end
    end
    return "chOther"
end

--- Whether a chat event's line is one the addon hands to the program (the channel on, not an addon's
--- line, one's own lines only when they are on) - for the chat windows' fading too (ChatFade.lua).
function ns.Reads(event, guid, text, baseName, channelString)
    local db = ns.db
    local key = EVENTS[event]
    if not (db and db.enabled and key and db[key]) then return false end
    if event == "CHAT_MSG_CHANNEL" and db[ns.ChannelSetting(baseName, channelString)] == false then return false end
    if db.skipAddons ~= false and ns.AddonLine(text) then return false end
    return db.self or not (guid and guid ~= "" and guid == UnitGUID("player"))
end

-- Retail (12.x) keeps chat from addons in a dungeon or raid, in a boss fight, a Mythic+ or a PvP
-- match ("chat messaging lockdown"): the text, the sender and the GUID come as secret values, which no
-- addon can read - any string operation on one is an error. Such a line is not read; the chat window
-- shows it (ChatFade.lua); the player is told once while it lasts. WoW Forever has no such rule.
--- Whether any of the values is secret (retail's restrictions; never on a client without them).
function ns.Secret(...)
    local issecretvalue = rawget(_G, "issecretvalue")
    if not issecretvalue then return false end
    for i = 1, select("#", ...) do
        if issecretvalue((select(i, ...))) then return true end
    end
    return false
end

ns.secretTold = false
function ns.SecretLine()
    if ns.db.debug then ns.Diag("не отправлено (закрытый чат: подземелье, рейд, бой с боссом или PvP)") end
    if not ns.secretTold then
        ns.secretTold = true
        print(PREFIX .. "здесь игра закрывает чат от аддонов (подземелье, рейд, бой с боссом или PvP): он не "
            .. "озвучивается, строки видны в окне чата.")
    end
end

local function OnChat(event, text, sender, _, channelString, _, _, _, _, baseName, _, _, guid)
    local db = ns.db
    local key = EVENTS[event]
    if not (db.enabled and key) then return end
    if not db[key] then ns.Skip("тип чата выключен в настройках: " .. key, sender, text) return end
    if event == "CHAT_MSG_CHANNEL" then
        local setting = ns.ChannelSetting(baseName, channelString)
        if db[setting] == false then
            ns.Skip("этот канал выключен в настройках: " .. tostring(baseName or channelString), sender, text)
            return
        end
    end
    if guid and guid ~= "" and guid == UnitGUID("player") and not db.self then
        ns.Skip("свои сообщения выключены", sender, text)
        return
    end
    local addon = db.skipAddons ~= false and ns.AddonLine(text)
    if addon then
        ns.Skip("сообщение аддона " .. addon, sender, text)
        return
    end
    local race, sex, class
    if guid and guid ~= "" then
        local ok, _, englishClass, _, englishRace, gender = pcall(GetPlayerInfoByGUID, guid)
        if ok then race, sex, class = englishRace, gender, englishClass end
    end
    local channel = event == "CHAT_MSG_CHANNEL" and channelString or ""
    Remember(key, sender, race, sex, class, channel, text)
    ns.Send(key, sender, race, sex, class, channel, text)
end

local TESTS = {
    { "Громмаш", "Orc", 2, "WARRIOR", "Всем привет! Кто идёт в Мёртвые копи?" },
    { "Джайна", "Human", 3, "MAGE", "Нужен хил в пещеры, пишите в личку." },
    { "Брэнн", "Dwarf", 2, "HUNTER", "Куплю землекорень, пять штук." },
    { "Тиранда", "NightElf", 3, "PRIEST", "Готовы? Пулю через три секунды." },
}

function ns.Test()
    for _, t in ipairs(TESTS) do ns.Send("test", t[1], t[2], t[3], t[4], "", t[5]) end
    print("|cff66ccffWoW Chat Voice|r: отправлено " .. #TESTS .. " тестовых строки.")
end

--- Silence now: the program cuts the line being said and drops what is waiting (/wcv stop).
function ns.Stop()
    local options = ns.LineOptions()
    ns.Strip.PushNow(table.concat({ "stop", "", "", "", "", "", options, "-" }, SEP))
end

local function Version()
    local meta = C_AddOns and C_AddOns.GetAddOnMetadata or GetAddOnMetadata
    return meta and meta(ADDON, "Version") or "?"
end

-- What a version brought, in a few words, for the line after an update (CHANGELOG.md has it all).
ns.NEWS = {
    ["0.2.1"] = "окно чата можно прятать, пока на нём нет мыши; мост к компаньону можно перенести; при входе видно, "
        .. "работает ли озвучка",
}

--- The word at login: the welcome on the first run, a line on what is new after an update (the
--- version last seen is kept), and every time whether the reading works (Companion.lua).
function ns.LoginWord()
    local version = Version()
    if ns.firstRun then
        ns.Welcome()
    elseif ns.db.seenVersion ~= version then
        print(PREFIX .. ("обновление %s: %s. Настройки — /wcv."):format(version, ns.NEWS[version]
            or "что нового — в описании аддона"))
    end
    ns.db.seenVersion = version
    if ns.Companion then ns.Companion.SayAtLogin() end      -- a file new in 0.2.1: after a game restart
end

--- The first run's word (as CatQuest does it): what this is, that it needs the companion app, where
--- the settings are.
function ns.Welcome()
    local version = Version()
    print(PREFIX .. ("|cffffd100добро пожаловать!|r WoW Chat Voice %s — озвучка чата: у каждого игрока свой голос "
        .. "его расы и пола."):format(version))
    print(PREFIX .. "читает вслух приложение-компаньон WoW Chat Voice (Windows): без него аддон молчит. Удобнее всего "
        .. "запускать игру через него — оно само запустит игру.")
    print(PREFIX .. "настройки — значок у миникарты или /wcv; команды — /wcv help.")
end

function ns.SetEnabled(enabled)
    ns.db.enabled = enabled and true or false
    if ns.db.enabled then
        ns.Strip.SetShown(true)
    else
        -- the stop has to be on the strip long enough to be read before the strip goes
        ns.Stop()
        if C_Timer then
            C_Timer.After(0.5, function() if not ns.db.enabled then ns.Strip.SetShown(false) end end)
        else
            ns.Strip.SetShown(false)
        end
    end
    if ns.Minimap then ns.Minimap.Refresh() end
    if ns.Options.Refresh then ns.Options.Refresh() end
    if ns.ChatFade then ns.ChatFade.Apply() end     -- the chat is not read aloud: show it
    print(PREFIX .. "озвучка чата " .. (ns.db.enabled and "включена" or "выключена"))
end

local function Merge(into, defaults)
    for k, v in pairs(defaults) do
        if into[k] == nil then into[k] = v end
    end
    return into
end

local loader = CreateFrame("Frame")
loader:RegisterEvent("ADDON_LOADED")
local function OnEvent(self, event, name, ...)
    if event == "ADDON_LOADED" then
        if name ~= ADDON then return end
        ns.firstRun = WowChatVoiceDB == nil   -- no saved settings yet: a welcome at login
        WowChatVoiceDB = Merge(WowChatVoiceDB or {}, ns.DEFAULTS)
        ns.db = WowChatVoiceDB
        if ns.firstRun then ns.db.scale = 1 else ns.MigrateScale(ns.db) end   -- settings of the program's own scale
        ns.RestoreHistory()
        ns.Dictionary.Migrate(ns.db)
        ns.Dictionary.Rebuild()
        ns.Strip.Initialize()
        ns.Options.Initialize()
        if ns.ChatFade then ns.ChatFade.Initialize() end   -- a file new in 0.2.1: loaded after a game restart
        ns.Minimap.Update()
        self:UnregisterEvent("ADDON_LOADED")
        for e in pairs(EVENTS) do self:RegisterEvent(e) end
        self:RegisterEvent("PLAYER_LOGIN")
        return
    end
    if event == "PLAYER_LOGIN" then
        ns.LoginWord()
        ns.SendControl()   -- the companion loads the voices chosen here
        ns.SendDictionary(true)
        -- the layer the saved variables hold now (they are written at login and /reload)
        local _, saved = LayerSet()
        if C_Timer and C_Timer.NewTicker then
            C_Timer.NewTicker(0.25, ns.WatchCatQuest)
            -- For a program started after the game: the settings (a short frame) every 2 minutes.
            -- The dictionary layer - frames up to half a screen long - only when it changed in this
            -- session: otherwise the program reads the very same layer from the saved variables.
            C_Timer.NewTicker(120, function()
                ns.SendControl()
                local _, now = LayerSet()
                if now ~= saved then ns.SendDictionary(true) end
            end)
        end
        return
    end
    if EVENTS[event] and ns.db.enabled and ns.Secret(name, (...), (select(11, ...))) then
        ns.SecretLine()                -- retail: a dungeon, raid, boss fight or PvP keeps chat from addons
        return
    end
    if EVENTS[event] and ns.db.enabled then
        ns.secretTold = false
        local visible, why = Visible(event, name, ...)
        if not visible then ns.Skip(why, (...), name) return end
    end
    OnChat(event, name, ...)
end
loader:SetScript("OnEvent", OnEvent)
ns.OnEvent = function(event, ...) OnEvent(loader, event, ...) end   -- for the tests

SLASH_WOWCHATVOICE1 = "/wcv"
SlashCmdList.WOWCHATVOICE = function(msg)
    msg = (msg or ""):lower():gsub("^%s+", ""):gsub("%s+$", "")
    if msg == "help" or msg == "?" then
        local G = "|cffffd100"
        print(PREFIX .. "команды:")
        print("  " .. G .. "/wcv|r — окно настроек (то же: значок у миникарты)")
        print("  " .. G .. "/wcv on|r, " .. G .. "/wcv off|r — включить или выключить озвучку (выключение сразу обрывает фразу)")
        print("  " .. G .. "/wcv stop|r — замолчать сейчас и очистить очередь, не выключая")
        print("  " .. G .. "/wcv test|r — четыре тестовые строки разными голосами")
        print("  " .. G .. "/wcv last 5|r — ещё раз прочитать последние 5 строк чата (через текущий словарь)")
        print("  " .. G .. "/wcv debug|r — отладка: почему строка чата не прочитана — в журнал компаньона")
        print("  " .. G .. "/wcv help|r — этот список")
    elseif msg == "test" then
        ns.Test()
    elseif msg == "stop" then
        ns.Stop()
        print(PREFIX .. "замолкаю (очередь очищена).")
    elseif msg:match("^last") then
        ns.Replay(tonumber(msg:match("%d+")) or 5)
    elseif msg == "debug" then
        ns.db.debug = not ns.db.debug
        print(PREFIX .. (ns.db.debug
            and "отладка включена: строки чата, которые аддон не отправил, с причиной, и речь CatQuest и Wayfarer — в журнале компаньона (logs, «диагностика аддона»)."
            or "отладка выключена."))
    elseif msg == "on" or msg == "off" then
        ns.SetEnabled(msg == "on")
    else
        ns.Options.Toggle()
    end
end
