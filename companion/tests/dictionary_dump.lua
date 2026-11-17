-- The addon's dictionary as the companion's tests need it (test_addon_dictionary.py): run from
-- addon/BarrensVoice as `luajit dictionary_dump.lua <case>`. Writes, separated by "\0": D.DEFAULT,
-- D.Text(), the layer the saved variables keep (dictionaryUser), then each "dict" frame's payload
-- ns.SendDictionary puts on the strip. Cases: "none" (no edits), "edited" (an entry deleted, one
-- changed, a regex's reading changed, a word, a stem and a phrase added), "many" (enough added lines
-- for several parts), "long" (a word added and a line longer than a part).
local case = arg[1] or "none"
local ns = { db = {} }
local function stub() return setmetatable({}, { __index = function() return function() end end }) end
CreateFrame, StaticPopupDialogs, SlashCmdList = stub, {}, {}
dofile("../../companion/tests/toc.lua")(ns, { "Protocol.lua", "Strip.lua", "Dictionary.lua", "Text.lua", "Core.lua" })
local frames = {}
ns.Strip.Push = function(p) frames[#frames + 1] = p end
local D = ns.Dictionary
D.Migrate(ns.db)
D.Rebuild()               -- as at load (ADDON_LOADED): the saved variables' layer is there before any edit

if case == "edited" then
    -- picked from the default as it is, so a changed default does not break the case
    local words, regex = {}, nil
    for line in D.Text():gmatch("[^\n]+") do
        local key = D.KeyOf(line)
        if key and line:sub(1, 1) == "~" then regex = regex or line
        elseif key and not key:find("[ *]") then words[#words + 1] = line end
    end
    assert(#words >= 2 and regex, "the default has words and regexes")
    local text = "\n" .. D.Text()
    local function drop(line) text = text:gsub("\n" .. line:gsub("%p", "%%%0") .. "\n", "\n", 1) end
    local function swap(line, new) text = text:gsub("\n" .. line:gsub("%p", "%%%0") .. "\n", "\n" .. new:gsub("%%", "%%%%") .. "\n", 1) end
    drop(words[1])
    swap(words[2], words[2]:match("^(.-=)") .. "моя замена")
    swap(regex, regex:match("^(.*)=") .. "=своё чтение")
    text = text .. "абв=где\nзюзя*=з+юзя*\nмоя фраза=м+оя фр+аза\n~\\bх(\\d+)\\b=икс \\1\n"
    D.SetText(text:sub(2))
elseif case == "long" then
    local long = "~\\b(?:" .. ("оченьдлинноеслово|"):rep(30) .. "конец)\\b=длинное правило"
    D.SetText(D.Text() .. "абв=где\n" .. long .. "\n")
elseif case == "many" then
    local text = D.Text()
    for i = 1, 40 do text = text .. ("моёслово%d=очень длинная замена номер %d для проверки частей\n"):format(i, i) end
    D.SetText(text)
end

print = function() end   -- the chat's word on a long line
ns.SendDictionary(true)
io.write(table.concat({ D.DEFAULT, D.Text(), ns.db.dictionaryUser, unpack(frames) }, "\0"))
