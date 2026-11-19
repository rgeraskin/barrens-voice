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

C.Read(rawget(_G, "BarrensVoiceStatus"), time and time() or 0)

--- "running", "stopped" (no time, or an old one).
function C.State()
    if beat and math.abs(loadedAt - beat) <= C.FRESH then return "running" end
    return "stopped"
end

--- The line at login.
function C.SayAtLogin()
    local prefix = (ns.ICON and ns.ICON .. " " or "") .. "|cff66ccffBarrens Voice|r: "   -- with the icon (Core.lua)
    if C.State() == "running" then
        print(prefix .. "озвучка чата работает.")
    else
        print(prefix .. "Barrens Voice Launcher не запущен — чат будет озвучиваться, как только ты его запустишь.")
        if ns.db and ns.db.fadeChat then     -- its own line: easy to miss at the end of the first
            print(prefix .. "прозрачный чат пока выключен: включится только после /reload, когда заработает лаунчер.")
        end
    end
end

--- The state as the settings window says it - for information: the chat is read either way. What it changes is
--- the hidden chat (ChatFade.lua), which hides the windows only when the companion ran at login: then a /reload.
function C.Describe()
    if C.State() == "running" then return "при входе в игру лаунчер |cff40ff40был запущен|r" end
    return "при входе в игру лаунчер |cffffd100не был запущен|r"
        .. (ns.db and ns.db.fadeChat and " — прозрачный чат включится после /reload" or "")
end
