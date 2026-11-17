-- A chat line's text as the addon reads it: markup and emoticons cleaned, a question told apart, an
-- addon's line and a numbered channel recognised. Pure functions on strings and tables only, no WoW
-- API: this file is also loaded by the tests outside the game (companion/tests/text.lua).
local _, ns = ...
ns = ns or {}

-- The payload's field separator (the unit separator): Core.lua joins the fields with it.
local SEP = "\31"
ns.SEP = SEP

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
