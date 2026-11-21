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

-- The feelings smileys carry (ns.Feeling, «и смайлики» under the names).
local LAUGH, SMILE, SAD = "смеётся", "улыбается", "грустит"
local HEART, PUZZLED, CRY, SURPRISED = "показывает сердечко", "в недоумении", "плачет", "удивляется"
local FROWN, WINCE = "хмурится", "морщится"

--- A face made of letters and marks, as a whole word (never a part of one: «leo_orc», «10_000»): ^_^ ^^ ^-^ smile,
--- T_T Т_Т ;_; cry, O_o o_O О_о surprise (a side: one Russian О/о - two bytes - or one or two Latin O, o, 0), -_- -.-
--- a frown, >_< >.< a wince.
local function FaceFeeling(word)
    if word:match("^%^[_%-%.]?%^$") then return SMILE end
    if word == "-_-" or word == "-.-" then return FROWN end
    if word == ">_<" or word == ">.<" then return WINCE end
    if word == "T_T" or word == "\208\162_\208\162" or word == ";_;" then return CRY end
    local a, b = word:match("^([Oo0\208\190\158]+)_([Oo0\208\190\158]+)$")
    if a and #a <= 2 and #b <= 2 then return SURPRISED end
    return nil
end

--- A word without the marks after it («O_o!» - «O_o», «-_-…» - «-_-»), or as it is when it is nothing but marks.
local function Core(word)
    local core, before = word, nil
    repeat
        before = core
        core = core:gsub("[!%?%.,]+$", "")
        if core:sub(-3) == "\226\128\166" then core = core:sub(1, -4) end   -- «…», one character
    until core == before
    return core ~= "" and core or word
end

--- A face in a word, with brackets and marks round it («O_o!», «О_о))», «(T_T)»): its feeling, the brackets before it,
--- the brackets and marks after it; nil for any other word.
local function GluedFace(word)
    local trail = ""                                        -- «^^)…»: the «…» after it all
    while word:sub(-3) == "\226\128\166" do word, trail = word:sub(1, -4), "\226\128\166" .. trail end
    local head, face, tail = word:match("^(%(*)(.-)([%(%)!%?%.,]*)$")
    if face == "" then return nil end
    local ellipsis = face:match("^(.-)\226\128\166$")           -- «-_-…»
    if ellipsis and FaceFeeling(ellipsis) then face, tail = ellipsis, "\226\128\166" .. tail end
    local feeling = FaceFeeling(face)
    if feeling then return feeling, head, tail .. trail end
    return nil
end

--- Brackets used for feelings, not as brackets, read as a full stop (a \3 until the end, so a comma by it goes): ")"
--- "))" "(((" ":)" ":D" ";P", and the faces (^_^ T_T O_o -_- >_<) as whole words. Paired brackets round a part are a short pause either side (commas); round a part of a
--- word («бл(и)н») they go, and the word is read; a quest's number in its link («(3513)]») is left to the program.
function ns.Emoticons(text)
    -- ")(" "}{" "><" next to letters is an "х" in disguise (past the swear filter): "на)(уя"
    text = text:gsub("([\128-\191])[%)}>][%({<]([\208\209])", "%1х%2")
    text = text:gsub("^[%)}>][%({<]([\208\209])", "х%1"):gsub("(%s)[%)}>][%({<]([\208\209])", "%1х%2")
    -- faces: ^_^ ^^ T_T O_o -_- >_< (Latin or Russian letters), whole words only - a pause, as the other smileys (ns.Feeling
    -- may say them)
    text = text:gsub("%S+", function(word)
        local feeling, head, tail = GluedFace(word)
        if not feeling then return nil end
        return head .. "\3" .. tail:gsub("\226\128\166", "")  -- «(T_T)» «(.)»: the brackets' rules below
    end)
    -- :) :( :D ;) :-P :Р (Р - Russian). Lua patterns see bytes: a Russian letter in a [set] would be
    -- two loose bytes there and eat the first byte of any letter after a colon ("1:Сильный"), so it
    -- goes as a sequence; a letter smiley only when no letter follows it ("ссылка:Dota" stays).
    text = text:gsub("[:;=]%-?[%)%(]+", "\3")
    text = text:gsub("[:;=]%-?[DdPp]+%f[^%w\128-\255]", "\3")
    text = text:gsub("[:;=]%-?\208\160%f[^%w\128-\255]", "\3"):gsub("[:;=]%-?\209\128%f[^%w\128-\255]", "\3")
    text = text:gsub("[%(%)][%(%)]+", "\3")                 -- )) ((( )(
    -- «бл(и)н»: one or two Russian letters in brackets inside a word go with the word; anything longer is a pair
    -- («танк(опытный)нужен», «Рейд(20:00)сегодня»)
    for _, L in ipairs({ "[\208\209][\128-\191]", "%a" }) do              -- Russian or Latin («f(u)ck»)
        text = text:gsub("([%w\128-\255])%((" .. L .. ")%)([%w\128-\255])", "%1%2%3")
        text = text:gsub("([%w\128-\255])%((" .. L .. L .. ")%)([%w\128-\255])", "%1%2%3")
    end
    -- a quest's number before «]» stays in its brackets, whatever the other brackets are: the program's rule takes
    -- «(3513)]» out
    text = text:gsub("%((%d+)%)%s*%]", "\1%1\2]")
    local opens = select(2, text:gsub("%(", ""))
    local closes = select(2, text:gsub("%)", ""))
    if opens ~= closes then
        text = text:gsub("[%(%)]", "\3")                    -- a lone bracket: "привет)"
    elseif opens > 0 then
        -- parentheses round a part: a short pause either side, as it is said aloud («группа (через 5 мин) в ОП» -
        -- «группа, через 5 мин, в ОП»); none at the line's start or end («( это шутка )» - «это шутка»)
        text = text:gsub("%s*%(%s*", ", "):gsub("%s*%)%s*", ", ")
        text = text:gsub("^[,%s]+", ""):gsub("[,%s]+$", ""):gsub(",%s*([,%.!%?])", "%1"):gsub("([%.!%?])%s*,%s*", "%1 ")
    end
    text = text:gsub("\1(%d+)\2%]", "(%1)]")
    -- a smiley's pause (\3 so far): no comma by it («привет), как дела», «ну, :) да», «ну O_o, а я»), then a full stop;
    -- an abbreviation's «.» keeps its comma («и т.д., и т.п.»)
    -- «привет)как дела»: a space after it too
    text = text:gsub(",%s*\3", "\3"):gsub("\3%s*,", "\3"):gsub("\3\226\128\166", "\226\128\166")
    text = text:gsub("\3([%w\128-\255])", ". %1"):gsub("\3", ".")
    text = text:gsub("%s+%.", "."):gsub("%.%.+", "."):gsub("([!?])%.", "%1"):gsub("%.%s*([!?])", "%1")
    return text
end

-- Smileys as words («и смайлики» under the names): the feelings the chat's own smileys carry. Players type them in
-- brackets and letters, not pictures (none in 3835 lines of Forever's chat, 11-21.11.2026).
-- a line of several: the first of these it has
local ORDER = { LAUGH, CRY, SAD, WINCE, FROWN, SURPRISED, HEART, PUZZLED, SMILE }
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

--- How `count` brackets «)» in a row are read, `n` the setting (smileyBrackets, 2): fewer than n - nil (a pause), n - a
--- smile, more - a laugh: «спасибо)» nothing, «спасибо))» «И улыбается.», «спасибо)))» «И смеётся.»
local function Smiles(count, n)
    if count > n then return LAUGH end
    if count == n then return SMILE end
    return nil
end

--- What one word of a line feels, if it is a smiley: LAUGH (")))", ":D", "xD", "хД", ":)))"; brackets by Smiles), SMILE (")",
--- "))", ":)", "=)", "8)", ":3"), SAD ("(((", "(", ":(", "=(", "</3"), HEART ("<3", "<333"), PUZZLED ("=\\", ":/"), the faces (FaceFeeling);
--- nil for anything else.
local function TokenFeeling(token, n)
    local face, head, tail = GluedFace(token)                -- «O_o!», «T_T.», «(^_^)»: the face
    if face and #head == #(tail:match("^%)*")) and not tail:find("%(") then return face end
    token = Core(token)
    if token:match("^8%-?%)$") or token:match("^:3+$") then return SMILE end
    if token == "</3" then return SAD end
    if token:find("^<3") and token:gsub("<3+", "") == "" then return HEART end
    if token:match("^[:;=]%-?[\\/]+$") then return PUZZLED end
    local closes = token:match("^[:;=]?%-?(%)+)$")
    if closes then return Smiles(#closes, n or 2) or SMILE end
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
--- but smileys («)))», «:D :D», «(((»); the feeling with `alone` false for a line that ends in one - two ")" a smile,
--- three a laugh (Smiles), two "(", ":D", "xD", ":(", "<3", "=\\" («идём в рейд)))», «персональный((»); nil otherwise. One bracket or ":)" after
--- a phrase is the pause it always was. For a letter smiley at the end ("xD", "хд": Clean
--- keeps letters) the third value is the line without it, so it is not read out before the feeling.
function ns.Feeling(text, brackets)
    if type(text) ~= "string" then return nil end
    local line = text:gsub("^%s+", ""):gsub("%s+$", "")
    if line == "" then return nil end
    -- how many brackets in a row are a smile and a laugh, sadness (`brackets`, 2 by default: the saved `smileyBrackets`;
    -- at most 10, a /run typo must not build a huge pattern for every chat line)
    local n = math.max(1, math.min(10, math.floor(tonumber(brackets) or 2)))
    local seen, all = {}, true
    for token in line:gmatch("%S+") do
        local feeling = TokenFeeling(token, n)
        if not feeling then all = false break end
        seen[feeling] = true
    end
    if all then
        for _, feeling in ipairs(ORDER) do if seen[feeling] then return feeling, true end end
    end
    -- The smileys at the end, word by word from the last («ору xD ))», «люблю <3 <3»): each one goes from the text - the
    -- feeling says it, or (a smile) nothing does: «<3» is no «три». The feeling is the last strong one of them.
    local rest, feeling, cut, marks = line, nil, false, nil
    -- as many "(" as ")" in the line: parentheses («( это шутка )»), not smileys - as Clean keeps them
    local _, opens = line:gsub("%(", "")
    local _, closes = line:gsub("%)", "")
    local paired = opens > 0 and opens == closes
    while true do
        local last = rest:match("(%S+)$")
        if not last or Core(last) == "8)" then break end      -- «нас 8)», «сбор в 8)»: maybe a number, left as typed
        local core = Core(last)
        local sad, happy = core:match("^[%(]+$"), core:match("^[:;=]?%-?(%)+)$")
        if (sad or core:match("^[%)]+$")) and paired then break end
        local f
        if happy then                                       -- «)» «:)» a pause, «))» a smile, «)))» a laugh (Smiles)
            f = Smiles(#happy, n)
        elseif sad then                                     -- spaced «((»: sadness from n of them
            f = #sad >= n and SAD or nil
        else
            f = TokenFeeling(last, n)
            if not f then break end
            if f == SMILE then f = nil end
        end
        if f and (not feeling or feeling == SMILE) then feeling = f end   -- a smile yields: «ору xD ))» laughs
        -- the marks glued to the last smiley stay with the line: «ты тут )?» is still a question
        marks = marks or (last:sub(#Core(last) + 1):gsub(",", ""))
        rest, cut = rest:sub(1, #rest - #last):gsub("%s+$", ""), true
    end
    if marks and marks ~= "" and rest ~= "" and not rest:find("[%.!%?]$") then
        rest = rest:gsub("[,:;%-]+$", "") .. marks
    end
    if not feeling and not cut then
        -- brackets glued to the last word («говорил))», «персональный((»): Clean makes them a full stop
        local last = rest:match("(%S+)$")
        local run = not line:find("%(") and Core(last):match("(%)+)$")   -- «спасибо)))!» too
        local smiles = run and Smiles(#run, n)
        if smiles == LAUGH then return LAUGH, false end
        if Core(last):find(("%("):rep(n) .. "$") and not line:find("%)") then return SAD, false end
        -- a face with a bracket glued («O_o)», «привет T_T(»): the face's feeling; a smile only alone, as ever
        local face = GluedFace(last)
        if face and (face ~= SMILE or last == line) then return face, false end
        if smiles then return smiles, false end             -- «спасибо))»: «И улыбается.»
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
