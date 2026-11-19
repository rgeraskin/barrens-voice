-- The dictionary's layers (Dictionary.lua): the default plus the player's edits.
-- Run: mise run test-lua (from addon/BarrensVoice, it loadfiles the addon by relative path)
local ns = { db = {} }
dofile("../../companion/tests/toc.lua")(ns, { "Protocol.lua", "Dictionary.lua" })
local D = ns.Dictionary
local function has(text, s) return text:find(s, 1, true) ~= nil end
local function count(text, s)
    local n, i = 0, 1
    while true do
        local a, b = text:find(s, i, true)
        if not a then return n end
        n, i = n + 1, b + 1
    end
end
local function empty(e) return next(e.lines) == nil and next(e.removed) == nil and e.header == nil end
local GOLD = "~\\b(\\d+)\\s*(?:з|g)\\b=\\1 [золотой|золотых|золотых]"
local GOLD_KEY = "~\\b(\\d+)\\s*(?:з|g)\\b"

-- keys
assert(D.KeyOf("Лок = чернокнижник") == "лок")
assert(D.KeyOf("хардкор*=хардк+ор*") == "хардкор*")
assert(D.KeyOf(GOLD) == GOLD_KEY, D.KeyOf(GOLD))
assert(D.KeyOf("~(?<=через )(\\d+)\\s*с\\b=\\1 сек") == "~(?<=через )(\\d+)\\s*с\\b", "a regex with '=' inside")
assert(D.KeyOf("# комментарий") == nil and D.KeyOf("просто текст") == nil)
assert(D.KeyOf("# слово=как читать") == nil, "a comment with \"=\" is no entry either")

-- no edits yet: the default; saving it unchanged stores nothing
D.Migrate(ns.db)
assert(empty(ns.db.dictionaryEdits))
local fresh = D.Text()
assert(has(fresh, "кд=кулд+аун") and has(fresh, GOLD))
D.SetText(fresh)
assert(empty(ns.db.dictionaryEdits), "unchanged text: no edits")
assert(D.Text() == fresh, "stable")
assert(ns.db.dictionaryUser == "-", "no edits: an empty layer for the program")

-- the player deletes, changes, changes a regex's reading, adds
local mine = fresh:gsub("\nимба=имб%+а", ""):gsub("\nлок=чернокнижник", "\nлок=лок")
mine = mine:gsub((GOLD:gsub("%p", "%%%0")), ((GOLD_KEY .. "=\\1 голды"):gsub("%%", "%%%%"))) .. "абв=где\n"
D.SetText(mine)
local e = ns.db.dictionaryEdits
assert(e.removed["имба"] and e.lines["лок"] == "лок=лок" and e.lines["абв"] == "абв=где", "edits")
assert(e.lines[GOLD_KEY] and has(e.lines[GOLD_KEY], "голды"), "regex reading changed: same key")
assert(not e.removed[GOLD_KEY], "not a delete")
assert(count(D.Text(), GOLD_KEY .. "=") == 1, "one gold rule")
local layer = D.UserLayer()
assert(has(layer, "лок=лок") and has(layer, "абв=где") and has(layer, "!имба=имб+а"), "the layer for the program: " .. layer)
assert(has(layer, GOLD_KEY .. "=\\1 голды") and ns.db.dictionaryUser == layer, "kept for the program too")

-- a new default: changed entries, a new one, the player's edits kept, deletes kept
local saved = D.DEFAULT
D.DEFAULT = D.DEFAULT:gsub("\nкд=кулд%+аун", "\nкд=откат"):gsub("\nлок=чернокнижник", "\nлок=варлок")
    :gsub("\nимба=имб%+а", "\nимба=очень сильно") .. "новое=слово\n"
D.Invalidate()
local now = D.Text()
assert(has(now, "кд=откат"), "untouched entry follows the default")
assert(has(now, "лок=лок") and not has(now, "лок=варлок"), "edited entry wins")
assert(not has(now, "имба="), "deleted entry stays deleted")
assert(has(now, "новое=слово") and has(now, "абв=где"), "new default entry, own entry")
assert(count(now, GOLD_KEY .. "=") == 1, "still one gold rule")
D.DEFAULT = saved
D.Invalidate()

-- a renamed default regex: whoever edited the old one does not get the new one beside it
local shipped = D.RENAMED
D.RENAMED = { [GOLD_KEY] = "~\\b(\\d+)\\s*(?:з|g|gold)\\b" }
D.DEFAULT = D.DEFAULT:gsub((GOLD:gsub("%p", "%%%0")), "~\\b(\\d+)\\s*(?:з|g|gold)\\b=\\1 [золотой|золотых|золотых]")
D.Invalidate()
D.Migrate(ns.db)
assert(not has(D.Text(), "(?:з|g|gold)"), "the new gold rule not added beside the edited old one")
assert(has(D.Text(), "голды"), "the player's own kept")
D.RENAMED = shipped
D.DEFAULT = saved
D.Invalidate()

-- the renames shipped (D.RENAMED): the old key is gone from the default, each new key is in it
local defaultKeys = {}
for line in D.DEFAULT:gmatch("[^\n]+") do
    local key = D.KeyOf(line)
    if key then defaultKeys[key] = true end
end
for old, new in pairs(D.RENAMED) do
    assert(not defaultKeys[old], "renamed, yet still a default key: " .. old)
    assert(#D.RenamedTo(new) > 0, "renamed to nothing: " .. old)
    for _, key in ipairs(D.RenamedTo(new)) do assert(defaultKeys[key], "renamed to a key the default lacks: " .. key) end
end
assert(table.concat(D.RenamedTo("~a\n~b"), "|") == "~a|~b", "several keys in one string, as dictionary.json has them")

-- the old «к» rule became six: whoever deleted it gets none of them, whoever edited it keeps theirs alone
local OLD_K, MINE_K = [[~(\d+)\s*к\b]], [[~(\d+)\s*к\b=\g<1> тысяч]]
local function migrated(edits)
    local other = { db = { dictionaryEdits = edits } }
    dofile("../../companion/tests/toc.lua")(other, { "Protocol.lua", "Dictionary.lua" })
    other.Dictionary.Migrate(other.db)
    other.Dictionary.Migrate(other.db)                      -- at every load: the same again
    return other.Dictionary, edits
end

-- «|» in the edit box: the game keeps a typed one as «||»; the window escapes and unescapes, so the layer has «|»
assert(D.Escaped("~(а|б)=в") == "~(а||б)=в" and D.Unescaped("~(а||б)=в") == "~(а|б)=в")
for _, t in ipairs({ "", "a|b", "||", "|||", "x|cffff|r" }) do assert(D.Unescaped(D.Escaped(t)) == t, t) end
-- saved by beta 17 and before as typed: «||» once taken back, a regex's key with it; a header too
do
    local edits = { lines = { ["~\\b(тестраз||тестдва)\\b"] = "# моё\n~\\b(тестраз||тестдва)\\b=окей",
                              ["абв"] = "абв=где" }, removed = {}, header = "# мой || словарь" }
    local Dp, e = migrated(edits)
    assert(e.lines["~\\b(тестраз|тестдва)\\b"] == "# моё\n~\\b(тестраз|тестдва)\\b=окей", "the line and its key")
    assert(e.lines["~\\b(тестраз||тестдва)\\b"] == nil and e.lines["абв"] == "абв=где", "the old key gone, others kept")
    assert(e.header == "# мой | словарь")
    -- a real «||» typed twice (saved «||||»): «||» after the one migration - migrated() runs Migrate twice
    local _, twice = migrated({ lines = { ["~а||||б"] = "~а||||б=в" }, removed = {} })
    assert(twice.lines["~а||б"] == "~а||б=в" and twice.lines["~а|б"] == nil, "once only, kept by its mark")
    -- two edits that become one key: both kept, one after the other (as Blocks joins them), none lost
    local _, both = migrated({ lines = { ["~(а|б)"] = "~(а|б)=x", ["~(а||б)"] = "~(а||б)=y" }, removed = {} })
    local joined = both.lines["~(а|б)"]
    assert(joined and joined:find("~(а|б)=x", 1, true) and joined:find("~(а|б)=y", 1, true), tostring(joined))
    local db = { dictionaryEdits = e, dictionaryPipes = true }
    e.lines["~а||б"] = "~а||б=в"                            -- after the migration: left alone (once only)
    Dp.Migrate(db)
    assert(e.lines["~а||б"] == "~а||б=в", "once only")
    local layer = { db = { dictionaryEdits = { lines = { ["~(а||б)"] = "~(а||б)=в" }, removed = {} } } }
    dofile("../../companion/tests/toc.lua")(layer, { "Protocol.lua", "Dictionary.lua" })
    layer.Dictionary.Migrate(layer.db)
    layer.Dictionary.Rebuild()
    assert(layer.Dictionary.UserLayer() == "~(а|б)=в" and layer.db.dictionaryUser:find("~(а|б)=в", 1, true)
        and not layer.db.dictionaryUser:find("||", 1, true), "the program gets «|» at once: " .. layer.Dictionary.UserLayer())
end
print("pipes ok")

assert(#D.RenamedTo(D.RENAMED[OLD_K]) == 6, "the «к» rule's six")
local Dd, deleted = migrated({ lines = {}, removed = { [OLD_K] = true } })
assert(not deleted.removed[OLD_K], "the old key's mark goes")
local layer = Dd.SentLayer()
for _, key in ipairs(Dd.RenamedTo(Dd.RENAMED[OLD_K])) do
    assert(deleted.removed[key], "deleted: " .. key)
    assert(not has(Dd.Text(), "\n" .. key .. "="), "not back in the window: " .. key)
    assert(has(layer, "!" .. key .. "="), "the program is told: " .. key)
end
local De, edited = migrated({ lines = { [OLD_K] = MINE_K }, removed = {} })
assert(edited.lines[OLD_K] == MINE_K and has(De.Text(), MINE_K), "the edited old rule is the player's own")
for _, key in ipairs(De.RenamedTo(De.RENAMED[OLD_K])) do
    assert(edited.removed[key] and not has(De.Text(), "\n" .. key .. "="), "not beside the edited one: " .. key)
end
local Du, untouched = migrated({ lines = {}, removed = {} })
assert(next(untouched.removed) == nil and has(Du.Text(), "\n~(\\d+)к\\b=\\g<1>000"), "untouched: the new rules")

-- «НП» was a word (any case), the dungeon's case-sensitive regex now: a player's delete or edit of «нп» carries over
do
    local NP = [[~\b(?-i:НП)\b]]
    local Dn, deleted = migrated({ lines = {}, removed = { ["нп"] = true } })
    assert(deleted.removed[NP] and not deleted.removed["нп"], "deleted «нп»: the dungeon's regex deleted too")
    assert(not Dn.Text():find(NP .. "=", 1, true), "and not in the text")
    local _, edited = migrated({ lines = { ["нп"] = "нп=моя пучина" }, removed = {} })
    assert(edited.removed[NP] and edited.lines["нп"] == "нп=моя пучина", "edited «нп»: theirs kept alone")
end
-- «СМ» the same: a word (any case) once, the dungeon's case-sensitive regex now
do
    local SM = [[~\b(?-i:СМ)\b]]
    local Ds, deleted = migrated({ lines = {}, removed = { ["см"] = true } })
    assert(deleted.removed[SM] and not deleted.removed["см"], "deleted «см»: the dungeon's regex deleted too")
    assert(not Ds.Text():find(SM .. "=", 1, true), "and not in the text")
    local _, edited = migrated({ lines = { ["см"] = "см=мой монастырь" }, removed = {} })
    assert(edited.removed[SM] and edited.lines["см"] == "см=мой монастырь", "edited «см»: theirs kept alone")
end
print("dictionary layers ok")

-- the dictionary online (DictionaryOnline.lua, loaded before Dictionary.lua): the newer default wins
local function loaded(online)
    BarrensVoiceDictionaryOnline = online
    local other = { db = {} }
    assert(loadfile("Protocol.lua"))("BarrensVoice", other)
    assert(loadfile("Dictionary.lua"))("BarrensVoice", other)
    BarrensVoiceDictionaryOnline = nil
    return other.Dictionary
end
local newer = loaded({ revision = 5, renamed = { ["~old"] = "~new" }, text = "\nзюзябра=тест\n" })
assert(newer.DEFAULT:find("зюзябра=тест", 1, true) and newer.REVISION == 5 and newer.RENAMED["~old"] == "~new")
local same = loaded({ revision = 0, text = "\nзюзябра=тест\n" })                -- not newer than the addon's own
assert(not same.DEFAULT:find("зюзябра=тест", 1, true) and same.REVISION == 0)
assert(not loaded(nil).DEFAULT:find("зюзябра", 1, true))                         -- nothing fetched yet
-- an entry the newer default no longer has: the window keeps it only for who changed it (their own line)
local fewer = loaded({ revision = 5, text = "\nкд=кулд+аун\n" })
assert(fewer.Text():find("кд=кулд+аун", 1, true) and not fewer.Text():find("имба=", 1, true), "untouched: gone")
local db = { dictionaryEdits = { lines = { ["имба"] = "имба=имба" }, removed = {} } }
BarrensVoiceDictionaryOnline = { revision = 5, text = "\nкд=кулд+аун\n" }
local mine = { db = db }
assert(loadfile("Protocol.lua"))("BarrensVoice", mine)
assert(loadfile("Dictionary.lua"))("BarrensVoice", mine)
BarrensVoiceDictionaryOnline = nil
mine.Dictionary.Migrate(db)
assert(mine.Dictionary.Text():find("имба=имба", 1, true), "changed by the player: kept as theirs")
-- a rename to several keys comes from dictionary.json as one string, the keys joined by "\n"
local gone = { dictionaryEdits = { lines = {}, removed = { ["~old"] = true } } }
BarrensVoiceDictionaryOnline = { revision = 5, renamed = { ["~old"] = "~a\n~b" }, text = "\n~a=x\n~b=y\nкд=кулд+аун\n" }
local split = { db = gone }
assert(loadfile("Protocol.lua"))("BarrensVoice", split)
assert(loadfile("Dictionary.lua"))("BarrensVoice", split)
BarrensVoiceDictionaryOnline = nil
split.Dictionary.Migrate(gone)
assert(gone.dictionaryEdits.removed["~a"] and gone.dictionaryEdits.removed["~b"] and not gone.dictionaryEdits.removed["~old"])
assert(not split.Dictionary.Text():find("\n~a=", 1, true) and not split.Dictionary.Text():find("\n~b=", 1, true))
print("dictionary online ok")
