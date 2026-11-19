-- Chat events -> payload for the strip: kind, sender, race, sex, class, channel, options, text,
-- joined by the unit separator (\31); options are "key=value;..." (rate, voice). The companion
-- picks a voice by sender, race and sex. The text functions (Clean, IsQuestion...) are in Text.lua,
-- the chat's wait for the quest voice-overs (ns.Deliver) in QuestVoice.lua.
local ADDON, ns = ...

ns.DEFAULTS = {
    enabled = true,
    party = true,      -- party and party leader
    raid = true,       -- raid and raid leader
    warning = true,    -- raid warnings
    instance = true,   -- instance chat (dungeon finder groups, battlegrounds)
    say = true,
    yell = true,
    whisper = true,    -- whispers to you: characters' and Battle.net friends'; your own with `self`
    guild = true,
    officer = true,
    channels = true,   -- numbered channels: General, Trade, LookingForGroup, LocalDefense ...
    chGeneral = true,  -- ... which of them once "channels" is on: General,
    chTrade = true,    --     Trade,
    chLfg = true,      --     LookingForGroup,
    chDefense = true,  --     LocalDefense / WorldDefense,
    chOther = true,    --     any other numbered channel (a custom one)
    emote = true,      -- /e emotes
    fadeChat = false,  -- chat windows transparent until the mouse is over them (ChatFade.lua)
    fadeWhisper = true,  -- ... but a whisper shows the window though it is read aloud
    fadeGuild = true,  --     and so does a guild (or officer) line
    fadeGroup = true,  --     and a party, raid, raid warning or instance chat line
    skipAddons = true, -- lines other players' addons write for them (Questie, DBM...) are not read
    debug = false,     -- /bv debug: why a chat line was not sent, and CatQuest's speech, to the program's log
    self = true,       -- your own lines
    onlyVisible = true, -- only lines a chat window of yours shows (its message types and channels, chat filters)
    onlyActiveTab = false, -- ... and of the docked windows only the selected tab (separate windows still count)
    waitForCatQuest = true, -- hold chat lines while CatQuest or Wayfarer reads a quest; send them when it is done
    cell = 2,          -- strip cell size, physical pixels
    rows = 1,          -- strip rows of cells
    -- the strip's cells start at the "left" edge of it or the "right"
    stripFrom = "left",
    -- where the strip is: "bottom" (default), "top" or "custom" (stripX, stripY, stripWidth: physical
    -- pixels of its top left corner and its width) - for another addon drawing in the same place
    stripPlace = "bottom",
    stripX = 0,
    stripY = 0,
    stripWidth = 800,
    -- dictionaryEdits: the player's changes to the default slang dictionary (Dictionary.lua, layers)
    rate = 100,        -- reading speed, percent of the voice's own pace (50..200)
    volume = 100,      -- loudness, percent (0..200: over 100 the program boosts, easing the peaks), on top of the program's own `volume`
    minimapIcon = true,
    minimapAngle = 160, -- degrees on the minimap ring (CatQuest's sits at 200)
    newsWindow = true, -- after an update with something big, the «Что нового» window; off: the chat line (News.lua)
    sayNames = true,   -- "Name: text"
    sayVerb = true,    -- "Name says: text" (says / yells / whispers / writes, by chat kind)
    sayLastNames = true,  -- the whole name ("Ивар Седой"); off: up to the first space ("Ивар")
    sayWhere = true,   -- "Name writes in the guild: text" when the place changes (Core.lua Where)
    declension = true, -- the program declines dictionary replacements after prepositions (pymorphy3)
    voices = "f5",     -- "f5": race voices (F5-TTS, from the client's own voice-over); "sapi": Windows voices
    -- voiceOff: [Windows voice name] = true for voices switched off; nil until changed here (the
    -- program then uses its own defaults)
    -- resetVoices: true while a /bv reset-voices asked for with the addon off waits for /bv on
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
    CHAT_MSG_BN_WHISPER = "whisper",   -- a Battle.net friend's whisper (ns.BNetFriend tells who)
    CHAT_MSG_WHISPER_INFORM = "whisper",      -- one's own whisper (OWN: read with «Свои сообщения»)
    CHAT_MSG_BN_WHISPER_INFORM = "whisper",   -- one's own Battle.net whisper (OWN)
    CHAT_MSG_GUILD = "guild",
    CHAT_MSG_OFFICER = "officer",
    CHAT_MSG_CHANNEL = "channels",
    CHAT_MSG_EMOTE = "emote",
}

-- One's own whispers: the event's name, GUID (and a Battle.net whisper's bnSenderID) are the recipient's,
-- never used - the line is the player's (ns.PlayerSender, UnitGUID("player")), read only with «Свои сообщения»
-- and once the player's own sender is known from a line of theirs.
local OWN = { CHAT_MSG_WHISPER_INFORM = true, CHAT_MSG_BN_WHISPER_INFORM = true }
local SELF_WHO = "ты"   -- the debug log's "who" for one's own whisper before the player's sender is known

local SEP = ns.SEP   -- Text.lua
local VERBS = { say = "говорит", yell = "кричит", whisper = "шепчет", warning = "объявляет", test = "говорит" }
local NOT_ASKED = { yell = true, whisper = true, warning = true }   -- the verb stays even for a question
local PREFIX = "|cff66ccffBarrens Voice|r: "
ns.PREFIX = PREFIX   -- every line of the addon in the chat starts with it (News.lua too)
local ICON = "|TInterface\\AddOns\\BarrensVoice\\Media\\chat:14:14|t"   -- the bubble on a clear background (make_icon.py)
ns.ICON = ICON       -- before the prefix of every message's first line; a message's next lines go without it
local SAY = ICON .. " " .. PREFIX   -- a message's first line

-- The name before a line is followed by a mark (\4): the program drops it when the same character
-- goes on while their previous line is still being said or was just said (it knows when a line
-- ends; the addon does not) - several lines in a row heard as one speech. After an emote's name the
-- mark is \5: never dropped. Either way the program applies the dictionary to the line alone, not
-- to the name ("Лок" stays a name).
local NAME_MARK, KEPT_NAME_MARK = "\4", "\5"

-- Where a line was said (sayWhere, Text.lua ns.Place): said when the place differs from the last line's
-- (a line of any kind: a say line between two guild lines counts) or after PLACE_PAUSE seconds without a
-- line - a fresh start. A run of guild lines says «в гильдии» once.
local PLACE_PAUSE = 30
local lastPlace, lastLineAt

--- The place to say before this line, or nil; every line sent moves the state on.
local function Where(kind, channel)
    -- (retail's closed chat never gets here - OnEvent drops it - but a secret channel name is not looked at)
    local place = not ns.Secret(channel) and ns.Place(kind, channel) or nil
    local now = GetTime and GetTime() or 0
    local say = place and (place ~= lastPlace or lastLineAt == nil or now - lastLineAt >= PLACE_PAUSE)
    lastPlace, lastLineAt = place, now
    return ns.db.sayWhere and say and place or nil
end

local SESSION = ("%x%02x"):format((time and time() or 0) % 0x100000, math.random(0, 255))
local lineCount = 0

--- `spoken`: the name to say when it is not the sender's own (a Battle.net friend's: ns.BNetFriend).
function ns.Send(kind, sender, race, sex, class, channel, text, spoken)
    local raw = (text or ""):gsub(SEP, " ")
    text = ns.Clean(text or "")          -- the dictionary is the program's (it reads Dictionary.lua itself)
    if text == "" then ns.Skip("пусто после очистки разметки", spoken or sender, raw) return end
    local place = Where(kind, channel)
    if ns.db.sayNames and sender and sender ~= "" then
        -- the spoken name never has the realm ("short": «Вася», not the «Вася-Степи» the chat shows for
        -- another realm); the payload keeps the whole sender: a voice per character
        local name = spoken or Ambiguate and Ambiguate(sender, "short") or sender:match("^[^-]+")
        if not ns.db.sayLastNames then name = name:match("^%S+") or name end
        if kind == "emote" then
            text = name .. KEPT_NAME_MARK .. " " .. text   -- "Вася смеётся"
        elseif ns.db.sayVerb then
            local verb = VERBS[kind] or "пишет"
            if not NOT_ASKED[kind] and ns.IsQuestion(text) then verb = "спрашивает" end
            -- "Вася пишет в гильдии:"; the place goes with the name when the program drops it
            text = name .. " " .. verb .. (place and " " .. place or "") .. ":" .. NAME_MARK .. " " .. text
        else
            text = name .. (place and ", " .. place or "") .. ":" .. NAME_MARK .. " " .. text   -- "Вася, в гильдии:"
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

--- A note for the program's log (kind "diag": logged, never spoken) - what the addon dropped.
function ns.Diag(text)
    ns.Strip.Push(ns.ServiceFrame("diag", ns.LineOptions(), text))
end

-- Debug (/bv debug): each chat line the addon gets but does not send, with the reason, and when
-- CatQuest or Wayfarer starts and stops speaking - notes in the program's log, which has the time the chat lacks.
function ns.Skip(reason, sender, text)
    if not ns.db.debug then return end
    local who = ns.ShownSender(sender)
    text = (text or ""):gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", ""):gsub("|H.-|h(.-)|h", "%1")
    ns.Diag(("не отправлено (%s): %s: %s"):format(reason, who, ns.Protocol.TrimUTF8(text, 90)))
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

function ns.LineOptions(voice)
    return ("rate=%d;vol=%d;voice=%s"):format(ns.Effective(ns.db.rate, ns.RATE_BASE),
        ns.Effective(ns.db.volume, ns.VOLUME_BASE), voice or ns.db.voices or "f5")
end

--- The settings frame (not spoken): options (which voices to keep loaded), the Windows voices
--- switched off, and where the strip is (strip=x,y,width,height,screen width,screen height, physical
--- pixels).
function ns.ControlPayload()
    local options = ns.LineOptions() .. ";strip=" .. ns.Strip.Describe()
    if ns.db.voiceOff then
        local off = {}
        for name in pairs(ns.db.voiceOff) do off[#off + 1] = name end
        table.sort(off)
        options = options .. ";off=" .. table.concat(off, "|")
    end
    return ns.ServiceFrame("control", options, "-")
end

function ns.SendControl()
    ns.Strip.Push(ns.ControlPayload())
end

--- While the addon is off the strip takes nothing (Strip.lua): an action that asks the companion
--- for something says so instead of its usual word. True when off.
function ns.Off()
    if ns.db.enabled then return false end
    print(SAY .. "озвучка выключена, включи её: /bv on.")
    return true
end

-- The player's dictionary layer (their edits of the default: Dictionary.D.SentLayer) goes to the
-- program over the strip, in parts of at most DICT_PART bytes (cut at line ends), tagged with a
-- checksum of the whole layer: "id=..;part=i;of=n". Sent when it changes (2 s after the last edit),
-- at login, and every 2 minutes when it changed in this session (else a program started after the
-- game reads the same layer from the saved variables, which the game writes on /reload and logout).
-- The default itself the program reads from Dictionary.lua. A line longer than a part is left out of the
-- layer (D.SentLayer: of the frames, their id and the saved variables' copy alike); the player is told.
local DICT_PART = ns.Dictionary.MAX_LINE
local lastLayer
local longBefore = {}   -- the layer's long lines at the last send

--- The layer as sent, its id (CRC-16, hex) and the lines left out of it.
local function LayerSet()
    local text, long = ns.Dictionary.SentLayer()
    local bytes = {}
    for i = 1, #text do bytes[i] = text:byte(i) end
    return text, ("%04x"):format(ns.Protocol.CRC16(bytes)), long
end

--- Tell the player of a line left out of the layer - once, not at every pause while they type it: only
--- when the layer has more long lines than at the last send.
local function TellLong(long)
    local seen = {}
    for _, line in ipairs(longBefore) do seen[line] = true end
    if #long > #longBefore then
        for _, line in ipairs(long) do
            if not seen[line] then
                -- "|" starts the chat's markup: "||" shows one (a regex is full of them)
                print(SAY .. ("строка словаря длиннее %d байт, в лаунчер она не передаётся. Разбей её на "
                    .. "несколько: %s…"):format(DICT_PART, (ns.Protocol.TrimUTF8(line, 60):gsub("|", "||"))))
                break
            end
        end
    end
    longBefore = long
end

function ns.SendDictionary(force)
    local text, id, long = LayerSet()
    TellLong(long)
    if not force and id == lastLayer then return end
    lastLayer = id
    local parts, current = {}, ""
    for line in (text .. "\n"):gmatch("(.-)\n") do
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
        ns.Strip.Push(ns.ServiceFrame("dict", options, part))
    end
end

local layerTimer
function ns.DictionaryChanged()
    if not (C_Timer and ns.Strip and ns.db) then return end
    if layerTimer then layerTimer:Cancel() end
    layerTimer = C_Timer.NewTimer(2, function() layerTimer = nil; ns.SendDictionary(false) end)
end

--- Retail WoW (12.x), not Forever (1.x): by the client's interface version.
function ns.Retail()
    local ok, _, _, _, interface = pcall(GetBuildInfo)
    return ok and (tonumber(interface) or 0) >= 100000 or false
end

-- Pages the settings link to (the «Помощь» tab, more voices on «Голоса»). An addon can neither open a
-- browser nor put text on the clipboard (LaunchURL and CopyToClipboard are Blizzard's own), so the
-- companion does both on a click: the addon sends only the name, and the companion keeps its own
-- list of the same addresses (bv/links.py) and touches nothing else. The address also stands in a
-- box in the settings, to select and copy with Ctrl+C when the companion is not running. A third field is
-- a Battle.net community's invite (club ticket): «Открыть» puts its link in the chat, one click opens it in
-- the game (LinkInChat).
ns.LINKS = {
    -- Barrens Voice's community in Battle.net (the game's «Сообщества»); the ticket is the invite address's code
    community = { "Сообщество", "https://launch.battle.net/invite/N9KR2WNHDgW", "N9KR2WNHDgW" },
    discord = { "Discord", "https://discord.gg/hxpuTQF2Bb" },
    telegram = { "Telegram", "https://t.me/+NwReoOS9x7hhYjgy" },
    github = { "GitHub", "https://github.com/rgeraskin/barrens-voice/issues" },
    rhvoice = { "RHVoice", "https://rhvoice.su/voices/" },
    silero = { "Silero", "https://github.com/snakers4/silero-models/releases?q=SAPI" },
    -- every release's changes in full (English; the «Что нового» window has the players' own words, News.lua)
    changelog = { "Изменения", "https://github.com/rgeraskin/barrens-voice/blob/master/CHANGELOG.md" },
}

local function AskCompanion(kind, key)
    ns.Strip.Push(ns.ServiceFrame(kind, ns.LineOptions(), key))
end

-- The community's word in the chat. The link is the client's own kind (LinkUtil.FormatLink with
-- LinkTypes.ClubTicket, as GetClubTicketLink makes it, in BATTLENET_FONT_COLOR - Forever and retail alike) with
-- a text of the addon's; each line starts with the addon's icon (Icon.tga without its bevelled frame: 4 of its
-- 64 pixels on each side). Every call here is open to addons in both clients' API docs (C_Club.IsEnabled,
-- GetSubscribedClubs, GetClubInfo and the event CLUB_ADDED: no HasRestrictions; the clubs' names can be secret
-- on retail, so they are looked at only when not).
local CLUB_LINK_COLOR = "|cff82c5ff"   -- BATTLENET_FONT_COLOR, when the client's own is not there
local GREY = "|cff999999"
local CLUB_NAME = "Barrens Voice"      -- how the community is told among the player's own
local JOIN_WAIT = 300                  -- seconds after «Открыть» a community joined is greeted
local askedAt                          -- when «Открыть» last gave the link

--- The invite as a chat link: "[Вступить в «Barrens Voice»]" in the colour of Battle.net's links; nil when the
--- client cannot make one.
local function ClubLink(ticket)
    local util, types = rawget(_G, "LinkUtil"), rawget(_G, "LinkTypes")
    if type(util) ~= "table" or type(util.FormatLink) ~= "function" or type(types) ~= "table" or not types.ClubTicket then
        return nil
    end
    local ok, link = pcall(util.FormatLink, types.ClubTicket, "[Вступить в «" .. CLUB_NAME .. "»]", ticket)
    if not ok or type(link) ~= "string" then return nil end
    local color = rawget(_G, "BATTLENET_FONT_COLOR")
    if type(color) == "table" and type(color.WrapTextInColorCode) == "function" then
        local fine, wrapped = pcall(color.WrapTextInColorCode, color, link)
        if fine and type(wrapped) == "string" then return wrapped end
    end
    return CLUB_LINK_COLOR .. link .. "|r"
end

--- Whether a club's info is Barrens Voice's community: its name, when it can be looked at (not secret).
local function OurClub(info)
    local canaccesstable = rawget(_G, "canaccesstable")
    if ns.Secret(info) or type(info) ~= "table" or (canaccesstable and not canaccesstable(info)) then return nil end
    local name = info.name
    if ns.Secret(name) or type(name) ~= "string" then return nil end
    return name:find(CLUB_NAME, 1, true) and name or false
end

--- The name of the player's own community that is Barrens Voice's (C_Club.GetSubscribedClubs), or nil.
local function JoinedName()
    local club = rawget(_G, "C_Club")
    if type(club) ~= "table" or type(club.GetSubscribedClubs) ~= "function" then return nil end
    local ok, name = pcall(function()
        local clubs = club.GetSubscribedClubs()
        local canaccesstable = rawget(_G, "canaccesstable")
        if ns.Secret(clubs) or type(clubs) ~= "table" or (canaccesstable and not canaccesstable(clubs)) then return nil end
        for _, info in ipairs(clubs) do
            local ours = OurClub(info)
            if ours then return ours end
        end
    end)
    return ok and name or nil
end

--- The key the player has for the guild and communities window (the binding TOGGLEGUILDTAB -> ToggleGuildFrame ->
--- ToggleCommunitiesFrame, both clients), as the client writes it (GetBindingKeyForAction, BindingUtil.lua), or nil.
--- Its default key is not in the UI source, so the key bound is asked, not assumed.
local function CommunitiesKey()
    local ok, key = pcall(rawget(_G, "GetBindingKeyForAction") or error, "TOGGLEGUILDTAB")
    return ok and not ns.Secret(key) and type(key) == "string" and key ~= "" and key or nil
end

--- A joined community (CLUB_ADDED) within JOIN_WAIT seconds of «Открыть»: greeted, if it is this one (or its name
--- cannot be looked at).
function ns.OnClubAdded(clubId)
    if not askedAt or (GetTime and GetTime() or 0) - askedAt > JOIN_WAIT then return end
    local club = rawget(_G, "C_Club")
    if type(club) == "table" and type(club.GetClubInfo) == "function" and not ns.Secret(clubId) then
        local ok, info = pcall(club.GetClubInfo, clubId)
        if ok and OurClub(info) == false then return end   -- another community joined meanwhile
    end
    askedAt = nil
    local key = CommunitiesKey()
    print(SAY .. "ты в сообществе!" .. (key and (" Окно сообществ — клавиша «%s»."):format(key) or ""))
end

--- A community's invite as a link in the chat, for the player to click: the click is the game's own
--- (ItemRefHandlersShared.lua: LinkTypes.ClubTicket -> CommunitiesHyperlink.OnClickLink, which asks for the
--- ticket and on CLUB_TICKET_RECEIVED opens the «Сообщества» window on the community). The addon does not
--- call that itself: the ticket listener it creates would then be the addon's, and every later invite
--- click would open the window from addon code (taint). A player already in the community is told so
--- instead. No companion needed, so it works with the voice-over off too. False when the client has no
--- communities or they are off: the browser it is, then.
local function LinkInChat(link)
    local ticket = link[3]
    local club = rawget(_G, "C_Club")
    if not ticket or type(club) ~= "table" or type(club.IsEnabled) ~= "function" then return false end
    local ok, enabled = pcall(club.IsEnabled)
    if not (ok and enabled) then return false end
    local joined = JoinedName()
    if joined then
        local key = CommunitiesKey()
        -- "|" starts the chat's markup: "||" shows one
        print(SAY .. ("ты уже в сообществе «%s»"):format((joined:gsub("|", "||")))
            .. (key and (" — окно сообществ открывается клавишей «%s»."):format(key) or "."))
    else
        local chatLink = ClubLink(ticket)
        if not chatLink then return false end
        print(SAY .. "сообщество в Battle.net — новости, вопросы, ошибки: " .. chatLink .. "  " .. GREY
            .. "или в браузере: " .. link[2] .. "|r")
        print(PREFIX .. "щёлкни по ссылке: откроется окно сообществ с кнопкой «Вступить». Не открылось — рядом ссылка для "
            .. "браузера.")
        askedAt = GetTime and GetTime() or 0
    end
    -- the settings close so the line is in sight (a hidden chat shows for a line like this one: ChatFade.lua);
    -- the click itself must be the player's: the game opens a community only from its own chat link
    if ns.Options and ns.Options.Hide then ns.Options.Hide() end
    return true
end

--- Ask the companion to open one of ns.LINKS in the browser; the address goes to the chat too. A
--- community's invite goes to the chat as a link to click (LinkInChat), where the client can.
function ns.OpenLink(key)
    local link = ns.LINKS[key]
    if not link then return end
    if LinkInChat(link) then return end
    if not ns.db.enabled then
        print(SAY .. ("%s: озвучка выключена, и лаунчер страницу не откроет. Адрес: %s"):format(link[1], link[2]))
        return
    end
    AskCompanion("open", key)
    print(SAY .. ("%s: Barrens Voice Launcher откроет страницу в браузере. Если не открылась (он не запущен) — адрес: %s")
        :format(link[1], link[2]))
end

--- Ask the companion to put one of ns.LINKS on the clipboard.
function ns.CopyLink(key)
    local link = ns.LINKS[key]
    if not link then return end
    if not ns.db.enabled then
        print(SAY .. ("%s: озвучка выключена, и лаунчер адрес не скопирует. Щёлкни по адресу в настройках и "
            .. "нажми Ctrl+C."):format(link[1]))
        return
    end
    AskCompanion("copy", key)
    print(SAY .. ("%s: Barrens Voice Launcher положит адрес в буфер обмена — вставь его в браузер (Ctrl+V). Если он не "
        .. "запущен, щёлкни по адресу в настройках и нажми Ctrl+C."):format(link[1]))
end

StaticPopupDialogs["BARRENSVOICE_RESET"] = {
    text = "Раздать голоса рас заново?\n\nЛаунчер забудет, у кого какой голос был, и выдаст их снова — "
        .. "так же, без повторов, начиная с тех, кто заговорит первым.",
    button1 = YES, button2 = NO,
    OnAccept = function() ns.ResetVoices() end,
    timeout = 0, whileDead = true, hideOnEscape = true, preferredIndex = 3,
}

--- Ask the program to forget which race voice each character had and hand them out afresh
--- (/bv reset-voices, asking first). While the addon is off the strip takes nothing: the reset waits
--- for the next /bv on (ns.SetEnabled), kept in the saved variables over a /reload. Unlike a test line
--- or a link, it is not heard and does not go stale - the player confirmed it and still wants it then.
function ns.ResetVoices()
    if not ns.db.enabled then
        ns.db.resetVoices = true
        print(SAY .. "озвучка выключена: голоса рас будут розданы заново, когда ты её включишь (/bv on).")
        return
    end
    ns.db.resetVoices = nil
    ns.Strip.Push(ns.ServiceFrame("reset", ns.LineOptions(), "-"))
    print(SAY .. "голоса рас будут розданы заново: каждый персонаж получит голос, когда заговорит.")
end

--- A test line in one Windows voice (the voices window's play buttons).
function ns.TestVoice(name)
    if ns.Off() then return end
    local options = ns.LineOptions("sapi") .. ";sapi=" .. name
    ns.Strip.Push(ns.ServiceFrame("test", options,
        "Привет! Нужен дам+агер в Мёртвые копи, продам сумки за пять тысяч.", "Проверка"))
end


function ns.SetVoices(value)
    ns.db.voices = value
    ns.SendControl()
    if not ns.db.enabled then        -- the settings go to the companion at /bv on
        print(SAY .. (value == "f5" and "голоса рас" or "голоса Windows")
            .. ". Озвучка переключится на них, когда ты её включишь (/bv on).")
    elseif value == "f5" then
        print(SAY .. "голоса рас. Модель загружается около 15 секунд, пока читают голоса Windows.")
    else
        print(SAY .. "голоса Windows. Модель голосов рас выгружается.")
    end
end

-- The last chat lines read, as they came (before the dictionary), for /bv last N. Kept in the saved
-- variables (written at /reload and logout), so they outlive a /reload and a game restart - not a
-- crash. The saved variables are the account's: another character replays the same lines. A Battle.net
-- friend's BattleTag is kept without its "#1234" (no friend's whole tag at rest on disk): a replayed line's
-- sender is "BN:Вася", which the companion ties to the voice of the "BN:Вася#1234" it knows (assign.py).
local HISTORY = 50
ns.history = {}

--- Take the history the saved variables kept (at load, once ns.db is there).
function ns.RestoreHistory()
    if type(ns.db.history) ~= "table" then ns.db.history = {} end
    ns.history = ns.db.history
    while #ns.history > HISTORY do table.remove(ns.history, 1) end
end

local function Remember(kind, sender, ...)
    if type(sender) == "string" and sender:find("^BN:") then sender = sender:gsub("#%d+$", "") end
    table.insert(ns.history, { n = select("#", ...) + 2, kind, sender, ... })   -- n: a nil (no race known) stays in place
    if #ns.history > HISTORY then table.remove(ns.history, 1) end
end

--- Read the last `n` chat lines again, through the current dictionary and settings.
function ns.Replay(n)
    if ns.Off() then return end
    n = math.max(1, math.min(n or 5, #ns.history))
    if #ns.history == 0 then
        print(SAY .. "пока нечего повторять: ни одной прочитанной строки чата.")
        return
    end
    -- marked replay=1: the companion drops none of them when its queue is full (live lines it may)
    ns.replaying = true
    for i = #ns.history - n + 1, #ns.history do
        local h = ns.history[i]
        ns.Send(unpack(h, 1, h.n))
    end
    ns.replaying = false
    print(SAY .. ("повторяю последние строки: %d."):format(n))
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

--- Whether a chat filter of another addon (a spam blocker and the like) hides this line in `frame`:
--- the client's own ChatFrameUtil.ProcessMessageEventFilters (Forever, retail: its first result says
--- "discard"), else the old clients' ChatFrame_GetMessageEventFilters(event) list. Another addon's
--- filter that errors counts as not hiding.
local function Filtered(frame, event, ...)
    local util = rawget(_G, "ChatFrameUtil")
    local ok, hidden
    if type(util) == "table" and type(util.ProcessMessageEventFilters) == "function" then
        ok, hidden = pcall(util.ProcessMessageEventFilters, frame, event, ...)
        hidden = ok and hidden and true or false
    else
        local get = rawget(_G, "ChatFrame_GetMessageEventFilters")
        local filters = type(get) == "function" and select(2, pcall(get, event))
        hidden = false
        for _, filter in ipairs(type(filters) == "table" and filters or {}) do
            local fine, hide = pcall(filter, frame, event, ...)
            if fine and hide then hidden = true break end
        end
    end
    return hidden
end

--- The tab selected in the main chat window (the dock of docked windows), when the player wants only it
--- read (onlyActiveTab); nil otherwise or on a client without the dock (then every tab counts).
local function SelectedTab()
    if not ns.db.onlyActiveTab then return nil end
    local get, dock = rawget(_G, "FCFDock_GetSelectedWindow"), rawget(_G, "GENERAL_CHAT_DOCK")
    if type(get) ~= "function" or not dock then return nil end
    local ok, selected = pcall(get, dock)
    return ok and selected or nil
end

-- Whispers have windows of their own: with the client's «Шёпот» option (CVar whisperMode) "popout" or
-- "popout_and_inline" each conversation gets a temporary window (FloatingChatFrame.lua
-- FloatingChatFrameManager_OnEvent -> FCF_OpenTemporaryWindow: ChatFrame11 and on, docked as a tab,
-- selected at once only for one's own whisper in "popout"), which takes that one target
-- (privateMessageList). With "popout" no other window shows a whisper (FCFManager_ShouldSuppressMessage), and a
-- window a conversation was moved out of leaves its target out (excludePrivateMessageList, except in
-- "popout_and_inline"; ChatFrameOverrides.lua MessageEventHandler). The same in Forever and retail.
local WHISPER_GROUPS = { WHISPER = true, BN_WHISPER = true }

local function Lower(s)
    local lower = rawget(_G, "strlower")   -- the client's own, as it keys the lists
    return type(lower) == "function" and lower(s) or s:lower()
end

local function WhisperMode()
    local get = rawget(_G, "GetCVar")
    local ok, mode = pcall(get or error, "whisperMode")
    return ok and type(mode) == "string" and mode or "inline"
end

--- Whether `frame` is the whisper window of this conversation (the client's dedicated frame).
local function OwnWhisperWindow(frame, group, target)
    return type(frame.chatType) == "string" and type(frame.chatTarget) == "string"
        and Lower(frame.chatType) == Lower(group) and Lower(frame.chatTarget) == target
end

--- Whether `frame`, which takes whispers, shows this one (to or from `target`, lowered) - the chat's own rules.
local function ShowsWhisper(frame, group, target, mode)
    if OwnWhisperWindow(frame, group, target) then return true end
    if mode == "popout" then return false end
    if type(frame.privateMessageList) == "table" and not frame.privateMessageList[target] then return false end
    if type(frame.excludePrivateMessageList) == "table" and frame.excludePrivateMessageList[target]
            and mode ~= "popout_and_inline" then
        return false
    end
    return true
end

--- The chat windows to look at: the ten permanent ones (shown or docked, by GetChatWindowInfo) and the
--- temporary whisper windows in use; each with whether it is docked.
local function ChatWindows()
    local list, named = {}, {}
    for i = 1, NUM_CHAT_WINDOWS or 10 do
        local frame = _G["ChatFrame" .. i]
        local shown, _, docked = select(7, GetChatWindowInfo(i))
        named["ChatFrame" .. i] = true
        if frame and (shown or docked) then list[#list + 1] = { frame, docked } end
    end
    for _, name in ipairs(type(CHAT_FRAMES) == "table" and CHAT_FRAMES or {}) do
        local frame = not named[name] and _G[name]
        if type(frame) == "table" and frame.isTemporary and frame.inUse then
            list[#list + 1] = { frame, frame.isDocked and true or false }
        end
    end
    return list
end

--- Whether the player sees this line: some chat window that is open (shown or docked as a tab)
--- takes it, and no chat filter - spam blockers and the like - hides it there. With onlyActiveTab a
--- docked window counts only while it is the selected tab; a separate (undocked) window always does.
--- A whisper counts in the windows that show that conversation, its own whisper window too - also one the
--- client is opening for it right now (when this addon hears the event first).
--- Frames are only compared here: retail's secret lines never get this far (OnEvent drops them).
local function Visible(event, ...)
    if not ns.db.onlyVisible or not GetChatWindowInfo then return true end
    local zoneChannel, baseName = select(7, ...), select(9, ...)
    local selected = SelectedTab()
    local group = ChatTypeGroupInverted and ChatTypeGroupInverted[event] or event:sub(10)
    local whisper = WHISPER_GROUPS[group] and type((select(2, ...))) == "string"
    local target, mode = whisper and Lower((select(2, ...))), whisper and WhisperMode()
    local seen, otherTab, ownWindow
    for _, item in ipairs(ChatWindows()) do
        local frame, docked = item[1], item[2]
        if whisper and OwnWhisperWindow(frame, group, target) then ownWindow = true end
        if Takes(frame, event, zoneChannel, baseName) and (not whisper or ShowsWhisper(frame, group, target, mode)) then
            if selected and docked and frame ~= selected then
                otherTab = true
            else
                seen = frame
                break
            end
        end
    end
    -- a conversation with no window yet in "popout" modes: the client opens one now, docked as a tab and
    -- not selected - but for one's own whisper in "popout" (FloatingChatFrameManager_OnEvent; not for a GM's)
    if not seen and whisper and not ownWindow and (mode == "popout" or mode == "popout_and_inline")
            and select(6, ...) ~= "GM" then
        if not selected or (mode == "popout" and event:find("_INFORM$")) then
            seen = rawget(_G, "DEFAULT_CHAT_FRAME") or ChatFrame1 or {}
        else
            otherTab = true
        end
    end
    if not seen then
        return false, otherTab and "не в выбранной вкладке чата" or "нет открытого окна чата с этим типом или каналом"
    end
    if Filtered(seen, event, ...) then return false, "скрыто фильтром чата другого аддона" end
    return true
end

ns.EVENTS = EVENTS   -- the chat events the addon reads (for the tests)

--- Whether a chat event's line is one the addon hands to the program (the channel on, not an addon's
--- line, one's own lines only when they are on, a Battle.net friend's only when the friend can be told by
--- `bnSenderID`) - for the chat windows' fading too (ChatFade.lua).
function ns.Reads(event, guid, text, baseName, channelString, bnSenderID)
    local db = ns.db
    local key = EVENTS[event]
    if not (db and db.enabled and key and db[key]) then return false end
    if event == "CHAT_MSG_CHANNEL" and db[ns.ChannelSetting(baseName, channelString)] == false then return false end
    if db.skipAddons ~= false and ns.AddonLine(text) then return false end
    if OWN[event] then return db.self == true and ns.PlayerSender() ~= nil end   -- the GUID is the recipient's
    if event == "CHAT_MSG_BN_WHISPER" and not ns.BNetFriend(bnSenderID) then return false end   -- OnChat drops it
    return db.self or not (guid and guid ~= "" and guid == UnitGUID("player"))
end

--- The player's GUID, nil when there is none to read (or it is secret).
local function PlayerGUID()
    local ok, guid = pcall(UnitGUID or error, "player")
    return ok and not ns.Secret(guid) and type(guid) == "string" and guid ~= "" and guid or nil
end

--- The player as the sender of their own whisper: the sender the game gave a chat line of the player's own
--- (say, guild, party...: the same voice as those lines), kept per character by GUID in the saved variables
--- (`ownSender`), so it outlives a /reload; nil until the character has written a line the addon heard.
--- Never built from UnitFullName: on Forever its second result may be the surname, not the realm (the
--- client's own FrameXMLUtil/Camelot/NameUtil.lua reads UnitName's so), and a "Name-Realm" made of it could
--- differ from what the chat gives - another voice for the same character.
function ns.PlayerSender()
    local guid, kept = PlayerGUID(), ns.db and ns.db.ownSender
    local sender = guid and type(kept) == "table" and kept[guid]
    return type(sender) == "string" and sender ~= "" and sender or nil
end

--- Keep the sender of the player's own line (any chat event the addon gets, before a setting drops it).
local function LearnOwnSender(event, sender, guid)
    if OWN[event] or ns.Secret(sender, guid) or type(sender) ~= "string" or sender == "" then return end
    local me = PlayerGUID()
    if not me or guid ~= me then return end
    if type(ns.db.ownSender) ~= "table" then ns.db.ownSender = {} end
    ns.db.ownSender[me] = sender
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
        print(SAY .. "здесь игра закрывает чат от аддонов (подземелье, рейд, бой с боссом или PvP): он не "
            .. "озвучивается, строки видны в окне чата.")
    end
end

-- Battle.net whispers: the event's sender (playerName) is a |K…|k token the chat shows as the friend's
-- real name - never said, sent or logged; the friend is told by the event's bnSenderID (ns.BNetFriend).
local BNET = { CHAT_MSG_BN_WHISPER = true }
local BNET_WHO = "друг Battle.net"   -- the debug log's "who" for a Battle.net line not sent

--- Who a Battle.net whisper is from, by its bnSenderID (C_BattleNet.GetAccountInfoByID, Forever and retail):
--- the friend's character when they play WoW (BNET_CLIENT_WOW) - its name to say, without the realm; the
--- payload's sender "Name-Realm", the voice of that character; its GUID, for race and sex - else the
--- BattleTag without its "#1234" to say and "BN:<BattleTag>" as the sender, no race. Never the account's
--- real name (accountName). nil when the friend cannot be told: no such API, nothing returned, or a value
--- that is secret (retail) - not looked at.
function ns.BNetFriend(id)
    if ns.Secret(id) or type(id) ~= "number" then return nil end
    local api = rawget(_G, "C_BattleNet")
    if type(api) ~= "table" or type(api.GetAccountInfoByID) ~= "function" then return nil end
    local canaccesstable = rawget(_G, "canaccesstable")
    local function open(t)
        return not ns.Secret(t) and type(t) == "table" and (not canaccesstable or canaccesstable(t))
    end
    local ok, friend = pcall(function()
        local info = api.GetAccountInfoByID(id)
        if not open(info) then return nil end
        local tag, game = info.battleTag, info.gameAccountInfo
        if ns.Secret(tag, game) then return nil end
        if open(game) then
            local client, character, realm, guid = game.clientProgram, game.characterName, game.realmName,
                game.playerGuid
            if not ns.Secret(client, character, realm, guid) and client == (rawget(_G, "BNET_CLIENT_WOW") or "WoW")
                    and type(character) == "string" and character ~= "" then
                -- the realm as the chat writes it after a name: no spaces ("Вася-ПиратскаяБухта")
                realm = type(realm) == "string" and realm:gsub("[%s%-]", "") or ""
                return { name = character, sender = realm ~= "" and character .. "-" .. realm or character,
                         guid = type(guid) == "string" and guid ~= "" and guid or nil }
            end
        end
        if type(tag) == "string" then
            local short = tag:match("^(.-)#") or tag
            if short ~= "" then return { name = short, sender = "BN:" .. tag } end
        end
        return nil
    end)
    return ok and friend or nil
end

local function OnChat(event, text, sender, _, channelString, _, _, _, _, baseName, _, _, guid, bnSenderID)
    local db = ns.db
    local key = EVENTS[event]
    if not (db.enabled and key) then return end
    local spoken          -- the name to say when it is not the sender's (a Battle.net friend's)
    local unknownSelf     -- one's own whisper before the player's sender is known
    if BNET[event] then
        local friend = ns.BNetFriend(bnSenderID)
        if not friend then ns.Skip("не удалось узнать, кто пишет в Battle.net", BNET_WHO, text) return end
        sender, spoken, guid = friend.sender, friend.name, friend.guid or ""
    elseif OWN[event] then
        -- the event's name and GUID are the recipient's: the line is said by the player, the recipient unnamed
        sender, guid = ns.PlayerSender(), PlayerGUID() or ""
        unknownSelf, sender = not sender, sender or SELF_WHO
    end
    if not db[key] then ns.Skip("тип чата выключен в настройках: " .. key, sender, text) return end
    if event == "CHAT_MSG_CHANNEL" then
        local setting = ns.ChannelSetting(baseName, channelString)
        if db[setting] == false then
            ns.Skip("этот канал выключен в настройках: " .. tostring(baseName or channelString), sender, text)
            return
        end
    end
    if (OWN[event] or guid and guid ~= "" and guid == UnitGUID("player")) and not db.self then
        ns.Skip("свои сообщения выключены", sender, text)
        return
    end
    if unknownSelf then
        -- (the game's sender for the player is not guessed: their whisper waits for a line of theirs)
        ns.Skip("твоё имя в чате ещё не известно: свой шёпот читается после твоей первой строки в чате", sender, text)
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
        if ok and not ns.Secret(englishClass, englishRace, gender) then
            race, sex, class = englishRace, gender, englishClass
        end
    end
    local channel = event == "CHAT_MSG_CHANNEL" and channelString or ""
    Remember(key, sender, race, sex, class, channel, text, spoken)
    ns.Send(key, sender, race, sex, class, channel, text, spoken)
end

local TESTS = {
    { "Громмаш", "Orc", 2, "WARRIOR", "Всем привет! Кто идёт в Мёртвые копи?" },
    { "Джайна", "Human", 3, "MAGE", "Нужен хил в пещеры, пишите в личку." },
    { "Брэнн", "Dwarf", 2, "HUNTER", "Куплю землекорень, пять штук." },
    { "Тиранда", "NightElf", 3, "PRIEST", "Готовы? Пулю через три секунды." },
}

function ns.Test()
    if ns.Off() then return end
    for _, t in ipairs(TESTS) do ns.Send("test", t[1], t[2], t[3], t[4], "", t[5]) end
    print(SAY .. "отправлено " .. #TESTS .. " тестовых строки.")
end

--- Silence now: the program cuts the line being said and drops what is waiting (/bv stop).
function ns.Stop()
    local options = ns.LineOptions()
    ns.Strip.PushNow(ns.ServiceFrame("stop", options, "-"))
end

local function Version()
    local meta = C_AddOns and C_AddOns.GetAddOnMetadata or GetAddOnMetadata
    return meta and meta(ADDON, "Version") or "?"
end

--- The word at login: every time whether the reading works (Companion.lua), and the welcome on the first run;
--- what is new after an update comes a few seconds later, out of combat (News.lua) - by the program's version,
--- which the companion wrote with the news (NewsData.lua), not the addon's.
-- The welcome waits a few seconds: at login every addon speaks at once, and the first lines scroll out of sight.
local WELCOME_DELAY = 5
-- Where to write about bugs and words read wrong: said at the first run, not at every login.
local HELP_HINT = "ошибки, неверное произношение, идеи — вкладка «Помощь» в настройках (/bv): там Discord, Telegram, GitHub и сообщество в Battle.net."

function ns.LoginWord()
    local installed = ns.News.Installed()      -- nil until the companion has written the news
    ns.News.Prepare(installed, ns.firstRun)    -- before the version last seen moves on
    if installed then ns.db.seenVersion = installed end
    ns.Companion.SayAtLogin()
    if ns.firstRun then
        if C_Timer then C_Timer.After(WELCOME_DELAY, ns.Welcome) else ns.Welcome() end
    end
    ns.News.AtLogin(installed)
end

--- The first run's word (as CatQuest does it): what this is, that it needs the companion app, where
--- the settings are.
function ns.Welcome()
    local version = Version()
    print(SAY .. ("|cffffd100добро пожаловать!|r Barrens Voice %s — озвучка чата: у каждого игрока свой голос "
        .. "его расы и пола."):format(version))
    print(PREFIX .. "читает вслух Barrens Voice Launcher — программа для Windows: без него аддон молчит. Удобнее всего "
        .. "запускать игру через него — он сам её запустит.")
    print(PREFIX .. "настройки — значок у миникарты или /bv. Команды — /bv help.")
    print(PREFIX .. HELP_HINT)
end

function ns.SetEnabled(enabled)
    ns.db.enabled = enabled and true or false
    if ns.db.enabled then
        -- the hidden strip took nothing: the settings and the dictionary layer afresh
        ns.Strip.SetShown(true)
        ns.SendControl()
        ns.SendDictionary(true)
        if ns.db.resetVoices then ns.ResetVoices() end   -- asked for while the addon was off
    else
        -- the stop has to be on the strip long enough to be read before the strip goes
        ns.Stop()
        ns.DropHeld()                 -- lines waiting for a quest voice-over are not read later either
        if C_Timer then
            C_Timer.After(0.5, function() if not ns.db.enabled then ns.Strip.SetShown(false) end end)
        else
            ns.Strip.SetShown(false)
        end
    end
    if ns.Minimap then ns.Minimap.Refresh() end
    if ns.Options.Refresh then ns.Options.Refresh() end
    ns.ChatFade.Apply()     -- the chat is not read aloud: show it
    print(SAY .. "озвучка чата " .. (ns.db.enabled and "включена" or "выключена"))
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
        ns.firstRun = BarrensVoiceDB == nil   -- no saved settings yet: a welcome at login
        BarrensVoiceDB = Merge(BarrensVoiceDB or {}, ns.DEFAULTS)
        ns.db = BarrensVoiceDB
        ns.RestoreHistory()
        ns.Dictionary.Migrate(ns.db)
        ns.Dictionary.Rebuild()
        ns.Strip.Initialize()
        ns.Options.Initialize()
        ns.ChatFade.Initialize()
        ns.Minimap.Update()
        self:UnregisterEvent("ADDON_LOADED")
        for e in pairs(EVENTS) do self:RegisterEvent(e) end
        self:RegisterEvent("PLAYER_LOGIN")
        pcall(self.RegisterEvent, self, "CLUB_ADDED")   -- a community joined (ns.OnClubAdded)
        return
    end
    if event == "CLUB_ADDED" then ns.OnClubAdded(name) return end
    if event == "PLAYER_LOGIN" then
        ns.LoginWord()
        ns.SendControl()   -- the companion loads the voices chosen here
        ns.SendDictionary(true)
        -- the layer the saved variables hold now (the game wrote them at the last logout or /reload)
        local _, saved = LayerSet()
        if C_Timer and C_Timer.NewTicker then
            -- the quest voice-overs (CatQuest, Wayfarer) are Forever's addons: no watching them on retail
            if not ns.Retail() then C_Timer.NewTicker(0.25, ns.WatchCatQuest) end
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
    -- text, sender, GUID (and a Battle.net whisper's bnSenderID; one's own whisper's, the recipient's, is
    -- not looked at)
    if EVENTS[event] and ns.db.enabled and (ns.Secret(name, (...), (select(11, ...)))
            or BNET[event] and ns.Secret((select(12, ...)))) then
        ns.SecretLine()                -- retail: a dungeon, raid, boss fight or PvP keeps chat from addons
        return
    end
    if EVENTS[event] then LearnOwnSender(event, (...), (select(11, ...))) end
    if EVENTS[event] and ns.db.enabled then
        ns.secretTold = false
        local visible, why = Visible(event, name, ...)
        if not visible then
            ns.Skip(why, BNET[event] and BNET_WHO or OWN[event] and (ns.PlayerSender() or SELF_WHO) or (...), name)
            return
        end
    end
    OnChat(event, name, ...)
end
loader:SetScript("OnEvent", OnEvent)
ns.OnEvent = function(event, ...) OnEvent(loader, event, ...) end   -- for the tests

SLASH_BARRENSVOICE1 = "/bv"
SlashCmdList.BARRENSVOICE = function(msg)
    msg = (msg or ""):lower():gsub("^%s+", ""):gsub("%s+$", "")
    if msg == "help" or msg == "?" then
        local G = "|cffffd100"
        print(SAY .. "команды:")
        print("  " .. G .. "/bv|r — окно настроек (то же: значок у миникарты)")
        print("  " .. G .. "/bv on|r, " .. G .. "/bv off|r — включить или выключить озвучку (выключение сразу обрывает фразу)")
        print("  " .. G .. "/bv stop|r — замолчать сейчас и очистить очередь, не выключая")
        print("  " .. G .. "/bv test|r — четыре тестовые строки разными голосами")
        print("  " .. G .. "/bv last 5|r — ещё раз прочитать последние 5 строк чата (через текущий словарь)")
        print("  " .. G .. "/bv debug|r — отладка: почему строка чата не прочитана — в журнал лаунчера")
        print("  " .. G .. "/bv reset-voices|r — раздать голоса рас заново (спросит)")
        print("  " .. G .. "/bv news|r — что нового в последних версиях")
        print("  " .. G .. "/bv help|r — этот список")
    elseif msg == "news" then
        ns.NewsWindow.Show()
    elseif msg == "test" then
        ns.Test()
    elseif msg == "stop" then
        if not ns.db.enabled then
            print(SAY .. "озвучка и так выключена.")   -- /bv off stopped it
        else
            ns.Stop()
            print(SAY .. "замолкаю (очередь очищена).")
        end
    elseif msg:match("^last") then
        ns.Replay(tonumber(msg:match("%d+")) or 5)
    elseif msg == "debug" then
        ns.db.debug = not ns.db.debug
        -- CatQuest and Wayfarer are Forever's addons: not a word of them on retail
        print(SAY .. (ns.db.debug
            and ("отладка включена: строки чата, которые аддон не отправил, с причиной%s — в журнале лаунчера "
                .. "(кнопка «Журнал» в окне Barrens Voice Launcher, строки «диагностика аддона»).")
                :format(ns.Retail() and "" or ", и речь CatQuest и Wayfarer")
            or "отладка выключена."))
    elseif msg == "on" or msg == "off" then
        ns.SetEnabled(msg == "on")
    elseif msg == "reset-voices" then
        StaticPopup_Show("BARRENSVOICE_RESET")
    else
        ns.Options.Toggle()
    end
end
