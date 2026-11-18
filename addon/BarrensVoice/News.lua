-- «Что нового»: what each addon version brought, for players (Russian, «ты»; CHANGELOG.md is the developers' English).
-- After an update, a few seconds after login and never in combat, the entries the player has not seen are shown
-- once: with a "big" one among them (a feature, something that works differently) the window, else ("small": fixes,
-- dictionary words) one chat line with the newest one's summary. Seen is kept per entry (`newsSeen` in the saved
-- variables, by the entry's version), so the first run marks everything seen: a newcomer gets the welcome instead.
--
-- An entry belongs to an addon version ("0.4.0"; a release of the program alone keeps the addon and its entry); a test build ("0.4.0b5") shows its release's entry, once, as soon as it
-- is written. An entry of a test build's own (version = "0.4.0b6") is shown from that build on: the way to tell the
-- testers who saw the release's entry already what a later build brought. Keep `version`, `date` and `kind` on an
-- entry's first line: tools/release.py reads them there (a release needs one for its addon, dated "DD.MM.YYYY").
local _, ns = ...

local N = {}
ns.News = N

N.ENTRIES = {
    { version = "0.4.0", kind = "big",   -- date: set at release
      title = "Установщик и обновления без хлопот",
      summary = "установщик с автообновлением, словарь онлайн, вкладка «Помощь» и шёпот Battle.net",
      items = {
        "Barrens Voice ставится установщиком (BarrensVoice-Setup.exe) и дальше обновляется сам — вместе с аддоном.",
        "Вместо консоли — окно Barrens Voice: работает ли озвучка, кнопка «Играть», журнал и настройки.",
        "Голоса рас работают не только на NVIDIA: нужна видеокарта с DirectX 12.",
        "Стандартный словарь обновляется сам, без обновления аддона.",
        "В настройках новая вкладка «Помощь»: сообщество Barrens Voice прямо в игре, Discord, Telegram и GitHub. "
            .. "Пиши туда, если что-то прочитано не так.",
        "Слышно, где написано: «Громмаш пишет в гильдии: …». Место звучит, только когда оно сменилось.",
        "Можно слушать только выбранную вкладку чата: вынеси группу в свою вкладку — и слышно только её. Это на "
            .. "вкладке «Каналы и чтение», в разделе «Что читать».",
        "Читается шёпот друзей по Battle.net, а со «Свои сообщения» — и твой собственный шёпот.",
        "Прозрачный чат показывается и на строке группы или рейда: в подземелье её легко пропустить. Это можно "
            .. "выключить.",
        "Barrens Voice теперь обращается к тебе на «ты».",
      } },
    { version = "0.3.0", date = "15.11.2026", kind = "big",
      title = "Ритейл и прозрачный чат",
      summary = "ритейл, прозрачный чат и галочка на каждый общий канал",
      items = {
        "Работает и в ритейле: у рас ритейла свои голоса из озвучки игры.",
        "У небеснорождённых теперь свои голоса.",
        "Окно чата можно прятать, пока на нём нет мыши: чат и так звучит.",
        "Общие каналы включаются по одному: можно слушать «Общий» без «Торговли».",
        "При входе в игру аддон говорит, работает ли озвучка.",
        "Сообщения аддонов других игроков (Questie, DBM и другие) не читаются.",
        "Вопрос звучит как «Громмаш спрашивает: …».",
        "Чат ждёт, пока Wayfarer дочитает квест, как и CatQuest.",
        "Настройки разложены по вкладкам.",
      } },
    { version = "0.2.1", date = "12.11.2026", kind = "small",
      title = "Одна речь на персонажа",
      summary = "несколько строк подряд от одного персонажа звучат одной речью",
      items = {
        "Несколько строк подряд от одного персонажа звучат одной речью: имя — только в начале.",
        "Мост к компаньону можно перенести: вверх, вниз или в своё место.",
        "Отладка: почему строка не прочитана — в журнале компаньона.",
        "«на 2 этаже» читается «на втором этаже».",
        "Когда CatQuest начинает читать квест, чат замолкает, а потом дочитывает строку с начала.",
      } },
    { version = "0.2.0", date = "11.11.2026", kind = "big",
      title = "Голоса рас из самой игры",
      summary = "голоса рас из русской озвучки самой игры",
      items = {
        "Голоса рас — из русской озвучки самой игры: у каждой расы и пола по 12 голосов.",
        "Пока CatQuest читает квест, чат ждёт.",
        "Замаскированные ругательства читаются как обычные слова.",
        "Ссылки на предметы и квесты читаются по названию.",
        "Медленные голоса говорят быстрее.",
      } },
    { version = "0.1.0", date = "11.11.2026", kind = "big",
      title = "Первый выпуск (тогда — WoW Chat Voice)",
      summary = "первый выпуск",
      items = {
        "Чат читается вслух, и у каждого игрока свой голос.",
        "Голоса рас (F5-TTS) или голоса Windows.",
        "Словарь сленга: WTS — «продам», дд — «дамагер».",
      } },
}

N.DELAY = 5            -- seconds after login: after the companion's word (Companion.lua), the chat settled
N.AFTER_COMBAT = 2     -- seconds after the combat ends: a pull right after another waits again

--- A version's parts: "0.4.0" -> { 0, 4, 0, huge }, "0.4.0b5" -> { 0, 4, 0, 5 } (a test build is older than its
--- release); nil for anything else ("?" when the client gave no version).
local function Parts(v)
    if type(v) ~= "string" then return nil end
    local a, b, c = v:match("^(%d+)%.(%d+)%.(%d+)$")
    if a then return { tonumber(a), tonumber(b), tonumber(c), math.huge } end
    local beta
    a, b, c, beta = v:match("^(%d+)%.(%d+)%.(%d+)b(%d+)$")
    if a then return { tonumber(a), tonumber(b), tonumber(c), tonumber(beta) } end
    return nil
end

--- -1, 0 or 1: "0.4.0b5" < "0.4.0" < "0.4.1"; nil when either is not a version.
function N.Compare(a, b)
    a, b = Parts(a), Parts(b)
    if not (a and b) then return nil end
    for i = 1, 4 do
        if a[i] ~= b[i] then return a[i] < b[i] and -1 or 1 end
    end
    return 0
end

--- The release a version leads to: "0.4.0b5" -> "0.4.0".
function N.Release(version) return (version:gsub("b%d+$", "")) end

--- For people: "0.4.0b5" -> "0.4.0 beta 5" (the launcher's install.display_version).
function N.Shown(version) return (version:gsub("b(%d+)$", " beta %1")) end

--- The entries the installed version has, newest first: a release's from its first test build on, a test build's
--- own from that build on. None when the version is not known.
function N.Visible(installed)
    if not Parts(installed) then return {} end
    local release = N.Release(installed)
    local out = {}
    for _, e in ipairs(N.ENTRIES) do
        local beta = type(e.version) == "string" and e.version:find("b%d+$")
        local order = N.Compare(e.version, beta and installed or release)
        if order and order <= 0 then out[#out + 1] = e end
    end
    table.sort(out, function(a, b) return N.Compare(a.version, b.version) > 0 end)
    return out
end

--- Set up the seen entries once (before the version last seen moves on): the first run sees everything; an addon
--- from before this list (only `seenVersion`) has seen what is not newer than that version - so a test build's
--- player sees the release's entry once.
function N.Prepare(installed, firstRun)
    local db = ns.db
    if type(db.newsSeen) == "table" then return end
    db.newsSeen = {}
    for _, e in ipairs(N.Visible(installed)) do
        local order = N.Compare(e.version, db.seenVersion)
        if firstRun or (order and order <= 0) then db.newsSeen[e.version] = true end
    end
end

--- The entries the installed version has that the player has not seen, newest first.
function N.Unseen(installed)
    local seen = type(ns.db.newsSeen) == "table" and ns.db.newsSeen or {}
    local out = {}
    for _, e in ipairs(N.Visible(installed)) do
        if not seen[e.version] then out[#out + 1] = e end
    end
    return out
end

-- The chat line's [Что нового]: a link of the clients' own "addon" type (LinkTypes.AddOn, LinkUtil.lua). A click
-- in a chat window goes ChatFrameMixin:OnHyperlinkClick -> SetItemRef -> LinkUtil.ProcessLink, whose handler for
-- the type (ItemRefHandlersShared.lua) only fires EventRegistry's "SetItemRef" and counts the link handled: no
-- ItemRefTooltip, and with Shift nothing goes into the edit box (SetItemRef's modified-click branch comes after).
-- EventRegistry calls each callback through securecallfunction, so the game's code is not tainted; ours only opens
-- our window. The same code in the forever and live branches of the UI source.
N.LINK = "addon:BarrensVoice:news"
local LINK_COLOR = "|cffffd100"

--- EventRegistry's "SetItemRef": our link opens the window, any other addon's link is left alone.
function N.OnLink(_, link)
    if ns.Secret(link) or link ~= N.LINK then return end
    if ns.NewsWindow then ns.NewsWindow.Show() end
end

do
    local registry, types = rawget(_G, "EventRegistry"), rawget(_G, "LinkTypes")
    if type(registry) == "table" and type(registry.RegisterCallback) == "function" and type(types) == "table"
            and types.AddOn == "addon" then
        N.linked = pcall(registry.RegisterCallback, registry, "SetItemRef", N.OnLink, N)
    end
end

--- Where the whole of it is, at the end of the chat line: the link, or the command where a click would go nowhere.
function N.More()
    if not N.linked then return "Что нового — /bv news." end
    return LINK_COLOR .. "|H" .. N.LINK .. "|h[Что нового]|h|r"
end

--- The chat line for an update: the addon's icon, «Barrens Voice:», the version and the newest entry's summary,
--- then where to read the rest (the «Что нового» window).
function N.ChatLine(entry, installed)
    return ns.ICON .. " " .. ns.PREFIX .. ("обновление %s — %s. %s"):format(N.Shown(installed), entry.summary, N.More())
end

--- What the player has not seen, shown now and marked seen: the window for a big entry (unless the setting
--- «Окно «Что нового» после обновлений» is off), else the chat line.
function N.Show(installed)
    local unseen = N.Unseen(installed)
    if #unseen == 0 then return end
    if type(ns.db.newsSeen) ~= "table" then ns.db.newsSeen = {} end
    local big = false
    for _, e in ipairs(unseen) do
        ns.db.newsSeen[e.version] = true
        if e.kind == "big" then big = true end
    end
    if big and ns.db.newsWindow ~= false and ns.NewsWindow then
        ns.NewsWindow.Show()
    else
        print(N.ChatLine(unseen[1], installed))
    end
end

local waiter   -- the frame that waits for the combat to end

--- Show the news now, or once out of combat (PLAYER_REGEN_ENABLED, then N.AFTER_COMBAT seconds, and again if a
--- new pull started meanwhile).
function N.Check(installed)
    if InCombatLockdown and InCombatLockdown() then
        waiter = waiter or CreateFrame("Frame")
        waiter:RegisterEvent("PLAYER_REGEN_ENABLED")
        waiter:SetScript("OnEvent", function(self)
            self:UnregisterEvent("PLAYER_REGEN_ENABLED")
            if C_Timer then C_Timer.After(N.AFTER_COMBAT, function() N.Check(installed) end) else N.Check(installed) end
        end)
        return
    end
    N.Show(installed)
end

--- After login (and /reload): the check, N.DELAY seconds later.
function N.AtLogin(installed)
    if C_Timer then C_Timer.After(N.DELAY, function() N.Check(installed) end) else N.Check(installed) end
end
