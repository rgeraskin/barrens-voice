-- A chat line's text as the addon reads it: markup and emoticons cleaned, a question told apart, an
-- addon's line and a numbered channel recognised; and the payload's service frames. Pure functions on
-- strings and tables only, no WoW API: this file is also loaded by the tests outside the game
-- (companion/tests/text.lua).
local _, ns = ...
ns = ns or {}

-- The payload's field separator (the unit separator): Core.lua joins the fields with it.
local SEP = "\31"
ns.SEP = SEP

--- A frame that is not a chat line (settings, a command to the companion, a note for its log): its
--- kind, options and text, with the sender's fields empty - or only the sender's name (`sender`, the
--- voices window's test line).
function ns.ServiceFrame(kind, options, text, sender)
    return table.concat({ kind, sender or "", "", "", "", "", options, text }, SEP)
end

--- A sender as /bv debug's notes name them: without the realm («Громмаш»), a Battle.net friend's
--- "BN:<BattleTag>" without the tag's "#1234" («BN:Вася»; the companion's log shows them so too); "?" for none.
function ns.ShownSender(sender)
    if type(sender) ~= "string" or sender == "" then return "?" end
    if sender:find("^BN:") then return (sender:gsub("#%d+$", "")) end
    return sender:match("^[^-]+") or sender
end

--- A line that is nothing but a question or questions ("кто в ОП?", "танк нужен? хил?"): no full stop,
--- exclamation mark or ellipsis anywhere, and it ends with "?". The voices rise at a question mark
--- unevenly, so such a line is announced "спрашивает" - the ear gets it from the verb.
function ns.IsQuestion(text)
    -- "…" is three bytes: in a [set] each would be a loose byte of other letters ("р", "Ц")
    return type(text) == "string" and text:find("%?%s*$") ~= nil and not text:find("[%.!]")
        and not text:find("…", 1, true)
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

-- Smileys as words («и смайлики» under the names): the feelings the chat's own smileys carry. Players type them in
-- brackets and letters, not pictures (none in 3835 lines of Forever's chat, 11-21.11.2026).
local LAUGH, SMILE, SAD = "смеётся", "улыбается", "грустит"
local HEART, PUZZLED = "показывает сердечко", "в недоумении"
-- a line of several: the first of these it has
local ORDER = { LAUGH, SAD, HEART, PUZZLED, SMILE }
-- "x" "X" "х" "Х" (Cyrillic, two bytes each in UTF-8) and "D" "d" "Д" "д": the letters of "xD" and "хД"
local X_LETTERS = { "x", "X", "\209\133", "\208\165" }
local D_LETTERS = { "D", "d", "\208\148", "\208\180" }

--- `token` with every leading `letters` (sequences of bytes) taken off once or more: what is left, and how many.
local function StripLetters(token, letters, once)
    local n = 0
    repeat
        local found = false
        for _, l in ipairs(letters) do
            if token:sub(1, #l) == l then token, n, found = token:sub(#l + 1), n + 1, true break end
        end
    until not found or (once and n > 0)
    return token, n
end

--- What one word of a line feels, if it is a smiley: LAUGH (")))", "))", ":D", "xD", "хД", ":))"), SMILE (")", ":)",
--- "=)", "8)", ":3"), SAD ("(((", "(", ":(", "=(", "</3"), HEART ("<3", "<333"), PUZZLED ("=\\", ":/"); nil for anything else.
local function TokenFeeling(token)
    if token:match("^8%-?%)$") or token:match("^:3+$") then return SMILE end
    if token == "</3" then return SAD end
    if token:find("^<3") and token:gsub("<3+", "") == "" then return HEART end
    if token:match("^[:;=]%-?[\\/]+$") then return PUZZLED end
    local closes = token:match("^[:;=]?%-?(%)+)$")
    if closes then return (#closes >= 2) and LAUGH or SMILE end
    if token:match("^[:;=]?%-?%(+$") then return SAD end
    if token:match("^[:;=]%-?[Dd]+$") then return LAUGH end
    local rest, x = StripLetters(token, X_LETTERS, true)
    if x == 1 then
        local tail, d = StripLetters(rest, D_LETTERS)
        if d > 0 and tail == "" then return LAUGH end
    end
    return nil
end

--- A line's smiley read as a feeling: «смеётся», «улыбается» or «грустит» with `alone` true for a line that is nothing
--- but smileys («)))», «:D :D», «(((»); the feeling with `alone` false for a line that ends in one - two or more ")"
--- or "(", ":D", "xD", ":(", "<3", "=\\" («идём в рейд))», «персональный((»); nil otherwise. One bracket or ":)" after
--- a phrase is the pause it always was. For a letter smiley at the end ("xD", "хд": Clean
--- keeps letters) the third value is the line without it, so it is not read out before the feeling.
function ns.Feeling(text, brackets)
    if type(text) ~= "string" then return nil end
    local line = text:gsub("^%s+", ""):gsub("%s+$", "")
    if line == "" then return nil end
    local seen, all = {}, true
    for token in line:gmatch("%S+") do
        local feeling = TokenFeeling(token)
        if not feeling then all = false break end
        seen[feeling] = true
    end
    if all then
        for _, feeling in ipairs(ORDER) do if seen[feeling] then return feeling, true end end
    end
    -- how many brackets at the end are a laugh or sadness (`brackets`, 2 by default: the saved `smileyBrackets`; at most
    -- 10, a /run typo must not build a huge pattern for every chat line)
    local n = math.max(1, math.min(10, math.floor(tonumber(brackets) or 2)))
    -- The smileys at the end, word by word from the last («ору xD ))», «люблю <3 <3»): each one goes from the text - the
    -- feeling says it, or (a smile) nothing does: «<3» is no «три». The feeling is the last strong one of them.
    local rest, feeling, cut = line, nil, false
    -- as many "(" as ")" in the line: parentheses («( это шутка )»), not smileys - as Clean keeps them
    local _, opens = line:gsub("%(", "")
    local _, closes = line:gsub("%)", "")
    local paired = opens > 0 and opens == closes
    while true do
        local last = rest:match("(%S+)$")
        if not last or last == "8)" then break end            -- «нас 8)», «сбор в 8)»: maybe a number, left as typed
        local brackets_ = last:match("^[%)]+$") or last:match("^[%(]+$")
        if brackets_ and paired then break end
        local f
        if brackets_ then                                   -- spaced brackets: a laugh or sadness from n of them
            f = #brackets_ >= n and (last:find("%)") and LAUGH or SAD) or nil
        else
            f = TokenFeeling(last)
            if not f then break end
            if f == SMILE then f = nil end
        end
        feeling = feeling or f
        rest, cut = rest:sub(1, #rest - #last):gsub("%s+$", ""), true
    end
    if not feeling and not cut then
        -- brackets glued to the last word («говорил))», «персональный((»): Clean makes them a full stop
        local last = rest:match("(%S+)$")
        if last:find(("%)"):rep(n) .. "$") and not line:find("%(") then return LAUGH, false end
        if last:find(("%("):rep(n) .. "$") and not line:find("%)") then return SAD, false end
        return nil
    end
    -- smiles only: the pause they always were (Clean made them a full stop)
    if not feeling and not rest:find("[%.!%?]$") and rest:sub(-3) ~= "…" then rest = rest:gsub("[,:;%-]+$", "") .. "." end
    return feeling, false, cut and rest or nil
end

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

-- Where a line was said, for «Громмаш пишет в гильдии: …» (Core.lua says it when the place changes). A raid
-- warning's verb is «объявляет», its place «рейду». Say, yell, whisper and emote have none: the verb says it.
-- Instance chat is a dungeon finder's or a battleground's group: «в группе» too.
local PLACES = { party = "в группе", raid = "в рейде", warning = "рейду", instance = "в группе",
                 guild = "в гильдии", officer = "в офицерском чате" }
local CHANNEL_PLACES = { chGeneral = "в общем", chTrade = "в торговле", chLfg = "в поиске спутников",
                         chDefense = "в обороне" }
-- after «пишет» a channel is where the line goes: «пишет в общий», not «пишет в общем», which sounds like the
-- writer's own «в общем» (so to say). «спрашивает в общем» reads well and stays
local CHANNEL_INTO = { chGeneral = "в общий", chTrade = "в торговлю", chLfg = "в поиск спутников",
                       chDefense = "в оборону" }
-- without a verb («Тралл, общий: …»): the channel's own name - «Тралл, в общем:» sounded like «so to say» too
local CHANNEL_NAMES = { chGeneral = "общий", chTrade = "торговля", chLfg = "поиск спутников", chDefense = "оборона" }
local CHANNEL_FORMS = { into = { CHANNEL_INTO, "в канал" }, name = { CHANNEL_NAMES, "канал" } }

--- The place of a line of `kind` ("в гильдии"), or nil. `channel`: a numbered channel's name as the chat
--- event gives it ("2. Торговля - Оргриммар", "5. мойканал"). `form`, for a numbered channel only (other places
--- are the same either way): "into" - where the line goes, after «пишет» ("в торговлю", "в канал мойканал");
--- "name" - the channel's name, with no verb ("торговля", "канал мойканал"); nil - where it is ("в торговле").
function ns.Place(kind, channel, form)
    if kind == "channels" then
        local places, word = unpack(CHANNEL_FORMS[form] or { CHANNEL_PLACES, "в канале" })
        local place = places[ns.ChannelSetting(nil, channel)]
        if place then return place end
        -- a channel of its own (or one not in the list): by its name, without the number and the zone
        local name = tostring(channel or ""):gsub("^%s*%d+%.%s*", ""):gsub("%s+%-%s+.*$", ""):gsub("%s+$", "")
        return name ~= "" and (word .. " " .. name) or word
    end
    return PLACES[kind]
end

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
