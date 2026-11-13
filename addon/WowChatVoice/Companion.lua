-- Is the companion app running? It writes the time into CompanionStatus.lua every 15 seconds (the
-- companion's status.py); the game reads that file - like every Lua file of an addon - at login and
-- /reload, so at those moments the addon knows, and says it in the chat once: "озвучка чата
-- работает", or that the companion is not running and the chat is read once it is started - the
-- strip is up all the time, so a companion started later reads it; the addon just cannot see that
-- until the next /reload, and says nothing it cannot know. During play there is no way back: sound files as flags (PlaySoundFile on an empty file and a valid one, as wow-ai
-- does) report every file present at the game's start as playable on the WoW Forever client.
local _, ns = ...

local C = {}
ns.Companion = C

C.FRESH = 45            -- seconds: three of the companion's writes; an older time - it is not running

local loadedAt, beat    -- when the status file was read (this file loads right after it) and its time

--- Take the status file's table as read at `at` (the game's time(): epoch seconds, as the companion's).
function C.Read(status, at)
    loadedAt = at
    beat = type(status) == "table" and tonumber(status.beat) or nil
end

C.Read(rawget(_G, "WowChatVoiceStatus"), time and time() or 0)

--- "running", "stopped" (no time, or an old one).
function C.State()
    if beat and math.abs(loadedAt - beat) <= C.FRESH then return "running" end
    return "stopped"
end

--- The line at login.
function C.SayAtLogin()
    local prefix = "|cff66ccffWoW Chat Voice|r: "
    if C.State() == "running" then
        print(prefix .. "озвучка чата работает.")
    else
        print(prefix .. "приложение-компаньон WoW Chat Voice не запущено — чат будет озвучиваться, как только вы его запустите.")
    end
end

--- The state as the settings window says it.
function C.Describe()
    if C.State() == "running" then return "|cff40ff40работает|r (при входе в игру)" end
    return "|cffffd100компаньон не был запущен|r при входе в игру — запустили позже: озвучка работает"
end
