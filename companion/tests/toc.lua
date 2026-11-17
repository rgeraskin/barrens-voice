-- The addon's files in the order BarrensVoice.toc lists them - the order the game loads them in. The
-- tests that run the addon load it through this, so a file moved in the .toc (Text.lua after
-- Core.lua: every chat line broken in the game) breaks them too. Run from addon/BarrensVoice.
--   local load = dofile("../../companion/tests/toc.lua")
--   load(ns)                                  -- every file, as the game does
--   load(ns, { "Protocol.lua", "Core.lua" })  -- only these, still in the .toc's order
local function Files()
    local toc = assert(io.open("BarrensVoice.toc"))
    local files = {}
    for line in toc:lines() do
        line = line:gsub("\r$", ""):match("^%s*(.-)%s*$")
        if line ~= "" and line:sub(1, 1) ~= "#" then files[#files + 1] = line end   -- "## Tag:" and comments
    end
    toc:close()
    assert(#files > 0, "BarrensVoice.toc lists no files")
    return files
end

return function(ns, only)
    local files, wanted = Files(), nil
    if only then
        wanted = {}
        for _, f in ipairs(only) do wanted[f] = true end
        local listed = {}
        for _, f in ipairs(files) do listed[f] = true end
        for _, f in ipairs(only) do assert(listed[f], f .. " is not in BarrensVoice.toc") end
    end
    for _, f in ipairs(files) do
        if not wanted or wanted[f] then assert(loadfile(f))("BarrensVoice", ns) end
    end
    return files
end
