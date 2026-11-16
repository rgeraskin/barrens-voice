-- The settings window (/bv, the minimap button, Options > AddOns), in the game's own tabs under the
-- frame (PanelTabButtonTemplate): "Общее" (the main switch, speed and volume, the chat windows, and the
-- foldable "Мост", StripWindow.lua), "Каналы и чтение", "Голоса" (the engine and the Windows voices,
-- VoicesWindow.lua) and "Словарь" (DictionaryWindow.lua). Each tab opens with a line on what is on it, and
-- the window is as high as the tab needs. One grid: the left column at LEFT, the right one at RIGHT_COL,
-- sub-options indented by SUB.
local _, ns = ...
local UI = ns.UI

local O = {}
ns.Options = O

local TITLE = "Barrens Voice"

-- What "Мост" is, for the player (the settings' button and the bridge window).
ns.BRIDGE_TIP = "Мост — то, через что аддон передаёт строки чата приложению-компаньону Barrens Voice, которое читает их вслух: тонкая тёмная линия у края экрана. Компаньон видит окно игры и читает эту линию — другого пути наружу у аддонов WoW нет. Если линию закрывает другой аддон (рисует что-то в том же месте), чат перестаёт читаться — тогда перенесите её."

-- The numbered channels, under "Общие каналы": setting, label, tooltip. No numbers: a channel's number is
-- the player's own (in the author's logs Trade was 2 in one town and 4 elsewhere, "Торговля (локальный)").
local NUMBERED = {
    { "chGeneral", "Общий", "Общий чат города или зоны." },
    { "chTrade", "Торговля", "Торговый канал: продажа, покупка, ремесло." },
    { "chLfg", "Поиск спутников", "Поиск группы и спутников." },
    { "chDefense", "Оборона", "Канал обороны: нападения на города и зоны." },
    { "chOther", "Остальные", "Любые другие номерные каналы, например ваши собственные." },
}

-- Channels, in two columns: setting, label, the client's slash command for it (the SLASH_<key>1..9 globals
-- the client defines, so the label shows what this client takes; the fallback if it has none), tooltip.
local CHANNELS = {
    { "party", "Группа", "PARTY", "/p", "Сообщения группы и её лидера." },
    { "say", "Сказать", "SAY", "/s", "Что говорят игроки рядом." },
    { "raid", "Рейд", "RAID", "/ra", "Сообщения рейда и его лидера." },
    { "yell", "Крик", "YELL", "/y", "Что кричат игроки рядом." },
    { "warning", "Объявления рейда", "RAID_WARNING", "/rw", "Объявления рейда." },
    { "whisper", "Шёпот", "SMART_WHISPER", "/w", "Шёпот вам." },
    { "instance", "Подземелье и БГ", "INSTANCE_CHAT", "/i", "Чат подземелья (поиск группы) и поля боя." },
    { "guild", "Гильдия", "GUILD", "/g", "Чат гильдии." },
    { "officer", "Офицеры", "OFFICER", "/o", "Офицерский чат гильдии." },
    { "emote", "Эмоции", "EMOTE", "/e", "Эмоции, написанные игроками." },
    { "self", "Свои сообщения", nil, nil, "Читать и ваши собственные строки." },
}

--- A channel's label with its slash command: "Группа (/гр)". Of the command's variants the client has
--- (ruRU: "/гр /группа /p /party"), the shortest in the client's own letters (not Latin), else the
--- shortest of all: "/р" for the raid, which the client lists after "/рейд".
local function ChannelLabel(item)
    if not item[3] then return item[2] end
    local best, bestLatin
    for i = 1, 9 do
        local v = rawget(_G, "SLASH_" .. item[3] .. i)
        if type(v) == "string" and v ~= "" then
            local latin = not v:find("[\128-\255]")
            if latin then
                if not bestLatin or #v < #bestLatin then bestLatin = v end
            elseif not best or #v < #best then
                best = v
            end
        end
    end
    return ("%s (%s)"):format(item[2], best or bestLatin or item[4])
end
O.ChannelLabel = ChannelLabel

local LEFT, RIGHT_COL, SUB = 18, 300, 26    -- the grid of every tab
local CHROME = 40                             -- the window's height beyond a tab's own: the title bar and the edge
local TOP, GAP = -14, 14                      -- the first text under the title bar; between a tab's blocks
local TEXT_W = 580 - 2 * LEFT - 8             -- the width of a tab's texts

local window, toggle, verb, lastNames, programState
local fadeSubs = {}   -- its sub-options: grey while the chat is not hidden
local numbered = {}   -- the check boxes of the numbered channels (grey while "Общие каналы" is off)
local checks, radios, sliders = {}, {}, {}
local tabs, tabButtons, tabOrder, tabHeight = {}, {}, {}, {}
local current = "general"
local bridgeHeight, bridgeOpen = 0, false

local TABS = {
    { "general", "Общее", "Включение озвучки, скорость и громкость, прозрачное окно чата и мост к компаньону." },
    { "reading", "Каналы и чтение", "Какие каналы и строки читать вслух и как произносить имена." },
    { "voices", "Голоса", "Чем читать: голоса рас или голоса Windows, и какие голоса Windows раздавать игрокам." },
    { "dictionary", "Словарь", "Как читать сленг и сокращения: WTS = продам, дд = дамагер, ОП = Огненная пропасть." },
    { "help", "Помощь", "Ошибки, улучшения, предложения, или что-то прочитано неправильно — пишите в Discord или Telegram.\n\n"
        .. "Или сразу заведите issue на GitHub |TInterface\\AddOns\\BarrensVoice\\Media\\smile:14:14|t" },
}

local function Refresh()
    if not window then return end
    toggle:SetText(ns.db.enabled and "|cff40ff40Озвучка чата включена|r" or "|cffff5050Озвучка чата выключена|r")
    if programState then
        programState:SetText(ns.Companion and ns.Companion.Describe() or "|cffaaaaaaКомпаньон: не проверить|r")
    end
    for _, c in ipairs(checks) do c.refresh() end
    for _, c in ipairs(numbered) do UI.SetCheckEnabled(c, ns.db.channels) end
    for _, c in ipairs(fadeSubs) do UI.SetCheckEnabled(c, ns.db.fadeChat) end
    UI.SetCheckEnabled(verb, ns.db.sayNames)
    if lastNames then UI.SetCheckEnabled(lastNames, ns.db.sayNames) end
    for value, r in pairs(radios) do r:SetChecked((ns.db.voices or "f5") == value) end
    for key, sl in pairs(sliders) do
        -- through the minimum: setting the value the slider already has does not move the thumb,
        -- and on the first show it was placed before the slider had its width
        local value = ns.db[key] or sl.default   -- before: SetValue(lo) writes lo into the setting
        sl.slider:SetValue(sl.lo)
        sl.slider:SetValue(value)
        ns.db[key] = value
        sl.show(value)
    end
end

local function Setting(key, after)
    return function() return ns.db[key] end, function(v)
        ns.db[key] = v
        if after then after(v) end
    end
end

--- The window as high as the shown tab needs (the first tab: with the bridge section if it is open).
local function Resize()
    if not window or not tabHeight[current] then return end
    local h = tabHeight[current] + CHROME
    if current == "general" and bridgeOpen then h = h + bridgeHeight end
    window:SetHeight(h)
end

--- Show the tab `name`: its frame, its tab marked, the window fitted to it.
local function Select(name)
    if not tabs[name] then name = "general" end
    current = name
    for _, key in ipairs(tabOrder) do
        local on = key == name
        tabs[key]:SetShown(on)
        local b = tabButtons[key]
        if b.native then
            if on then PanelTemplates_SelectTab(b) else PanelTemplates_DeselectTab(b) end
        elseif on then b:Disable() else b:Enable() end
    end
    Resize()
end

--- A line at the top of a tab on what is on it; returns the y the tab's content starts at.
local function Describe(tab, text)
    local _, height = UI.Text(tab, "GameFontDisable", LEFT + 4, TOP, TEXT_W, text)
    return TOP - height - GAP
end

-- "Общее": the main switch, trying the voices, whether the companion runs, speed and volume, the chat
-- windows, and the foldable "Мост".
local function BuildGeneral(tab, description)
    local y = Describe(tab, description)
    -- Three buttons of one size in a row: the main switch (green or red), trying the voices, handing
    -- the race voices out afresh.
    StaticPopupDialogs["BARRENSVOICE_RESET"] = {
        text = "Раздать голоса рас заново?\n\nКомпаньон забудет, у кого какой голос был, и выдаст их снова — "
            .. "так же, без повторов, начиная с тех, кто заговорит первым.",
        button1 = YES, button2 = NO,
        OnAccept = function() ns.ResetVoices() end,
        timeout = 0, whileDead = true, hideOnEscape = true, preferredIndex = 3,
    }
    local W, GAP = 176, 8
    toggle = UI.Button(tab, "", W, function() ns.SetEnabled(not ns.db.enabled) end)
    toggle:SetPoint("TOPLEFT", LEFT, y)
    UI.Tooltip(toggle, "Включить или выключить всю озвучку: мост к компаньону (линию у края экрана) и передачу чата "
        .. "ему. То же — ПКМ по значку у миникарты или /bv on, /bv off.")
    local test = UI.Button(tab, "Проверка", W, ns.Test)
    test:SetPoint("TOPLEFT", LEFT + W + GAP, y)
    UI.Tooltip(test, "Четыре тестовые строки разными голосами (/bv test). Все команды — /bv help.")
    local reset = UI.Button(tab, "Перераздать голоса", W, function() StaticPopup_Show("BARRENSVOICE_RESET") end)
    reset:SetPoint("TOPLEFT", LEFT + 2 * (W + GAP), y)
    UI.Tooltip(reset, "Раздать голоса рас заново: у каждого персонажа может оказаться другой голос.")
    y = y - 30
    local get, set = Setting("minimapIcon", function() ns.Minimap.Update() end)
    checks[#checks + 1] = UI.Check(tab, LEFT, y, "Значок у миникарты",
        "ЛКМ — эти настройки, ПКМ — включить или выключить озвучку.", get, set)
    y = y - 30

    programState = tab:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    programState:SetPoint("TOPLEFT", LEFT + 4, y)
    programState:SetPoint("RIGHT", -LEFT, 0)
    programState:SetJustifyH("LEFT")
    UI.TextTooltip(tab, programState, "Работало ли приложение-компаньон Barrens Voice, которое читает чат вслух, "
        .. "когда вы входили в игру: оно раз в 15 секунд отмечается в файле в папке аддона, а игра читает этот файл "
        .. "при входе и /reload. Запущенный позже компаньон тоже читает чат — аддон просто узнает об этом при "
        .. "следующем /reload.")
    y = y - 24

    y = UI.Header(tab, "Скорость и громкость", y)
    -- A labelled slider for a percent setting `key`, `lo`..`hi` in steps of `step`.
    local function Slider(key, title, lo, hi, step, tip)
        local label = tab:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
        label:SetPoint("TOPLEFT", LEFT + 4, y)
        local slider = CreateFrame("Slider", nil, tab)
        slider:SetOrientation("HORIZONTAL")
        slider:SetSize(240, 16)
        slider:SetPoint("TOPLEFT", RIGHT_COL, y + 2)
        slider:SetMinMaxValues(lo, hi)
        slider:SetValueStep(step)
        slider:SetObeyStepOnDrag(true)
        local track = slider:CreateTexture(nil, "BACKGROUND")
        track:SetColorTexture(1, 1, 1, 0.15)
        track:SetPoint("LEFT")
        track:SetPoint("RIGHT")
        track:SetHeight(4)
        slider:SetThumbTexture("Interface\\Buttons\\UI-SliderBar-Button-Horizontal")
        local function Show(value)
            label:SetText(("%s: |cffffd100%d%%|r"):format(title, value))
        end
        slider:SetScript("OnValueChanged", function(_, value)
            value = math.floor(value / step + 0.5) * step
            ns.db[key] = value
            Show(value)
        end)
        slider:EnableMouseWheel(true)
        slider:SetScript("OnMouseWheel", function(self, delta) self:SetValue(self:GetValue() + delta * step) end)
        UI.Tooltip(slider, tip)
        sliders[key] = { slider = slider, show = Show, default = 100, lo = lo }
        y = y - 30
    end
    Slider("rate", "Скорость чтения", 40, 160, 5,
        "Скорость чтения для всех голосов, от 40 до 160 %.")
    Slider("volume", "Громкость", 0, 200, 5,
        "Громкость озвучки, от 0 до 200 %: действует со следующей строки.")

    y = UI.Header(tab, "Окно чата", y)
    get, set = Setting("fadeChat", function() if ns.ChatFade then ns.ChatFade.Apply() end Refresh() end)
    checks[#checks + 1] = UI.Check(tab, LEFT, y, "Прятать окно чата, пока на нём нет мыши", "Чат и так "
        .. "звучит: окна чата (текст, фон, вкладки, поле ввода) прозрачны, пока на них не наведена мышь и вы ничего "
        .. "не пишете. Строка, которую компаньон не читает вслух — системное сообщение, добыча, выключенный канал, "
        .. "ваша собственная, сообщение аддона, — показывает окно на 10 секунд: то, чего не слышно, видно. "
        .. "Работает, пока озвучка включена.", get, set)
    for i, item in ipairs({
        { "fadeWhisper", "при шёпоте", "Шёпот вам показывает окно чата, хотя и озвучивается: его легко пропустить на слух." },
        { "fadeGuild", "при строке гильдии", "Строка гильдии (и офицерского чата) показывает окно, хотя и озвучивается." } }) do
        local g, s = Setting(item[1])
        local c = UI.Check(tab, LEFT + SUB + (i - 1) * 250, y - 24, "Показывать " .. item[2], item[3], g, s)
        checks[#checks + 1] = c
        fadeSubs[#fadeSubs + 1] = c
    end
    y = y - 54

    -- "Мост к компаньону": folded, as it is needed rarely - when another addon covers the line.
    y = UI.Header(tab, "Дополнительно", y)
    checks[#checks + 1] = UI.Check(tab, LEFT, y, "Отладка (/bv debug)", "Аддон пишет в журнал компаньона каждую "
        .. "строку чата, которую не отправил, с причиной (канал выключен, строку не видно ни в одном окне чата, "
        .. "её скрыл другой аддон), и когда CatQuest или Wayfarer начинает и заканчивает говорить. Строки отладки "
        .. "идут по мосту вместе с чатом, поэтому включайте её, только когда ищете, почему что-то не прочитано.",
        function() return ns.db.debug end, function(v) ns.db.debug = v end)
    y = y - 30
    local fold = UI.Button(tab, "", 272, nil)
    fold:SetPoint("TOPLEFT", LEFT, y)
    UI.Tooltip(fold, ns.BRIDGE_TIP)
    local bridge = CreateFrame("Frame", nil, tab)
    bridge:SetPoint("TOPLEFT", 0, y - 30)
    bridge:SetPoint("RIGHT", 0, 0)
    bridge:Hide()
    local function Fold(open)
        bridge:SetShown(open)
        bridgeOpen = open
        fold:SetText(open and "Мост к компаньону: свернуть" or "Мост к компаньону…")
        Resize()
    end
    fold:SetScript("OnClick", function() Fold(not bridge:IsShown()) end)
    if ns.StripWindow then
        bridgeHeight = ns.StripWindow.Create(bridge, function() Fold(false) end)
        bridge:SetHeight(bridgeHeight)
        O.Bridge = Fold
    else   -- a file new to the addon: the game loads it only after a restart, not on /reload
        fold:SetScript("OnClick", function()
            print("|cff40c0ffBarrens Voice:|r раздел «Мост» появится после перезапуска игры.")
        end)
    end
    fold:SetText("Мост к компаньону…")
    y = y - 34
    return -y
end

-- "Каналы и чтение": how a line is read, and which chats are read.
local function BuildReading(tab, description)
    local y = Describe(tab, description)
    y = UI.Header(tab, "Чтение", y)
    local get, set = Setting("sayNames", function() Refresh() end)
    checks[#checks + 1] = UI.Check(tab, LEFT, y, "Озвучивать имена", "Перед сообщением читать имя написавшего: "
        .. "«Громмаш: всем привет».", get, set)
    -- Forever only: retail names have no spaces, and CatQuest and Wayfarer are Forever's addons
    local retail, row = ns.Retail(), 1
    if not retail then
        get, set = Setting("sayLastNames")
        lastNames = UI.Check(tab, LEFT + SUB, y - 24 * row, "и фамилии: «Ивар Седой», а не «Ивар»", "Читать имя целиком. "
            .. "Выключено — только до первого пробела: у персонажа «Ивар Седой» прозвучит «Ивар».", get, set)
        checks[#checks + 1] = lastNames
        row = row + 1
    end
    get, set = Setting("sayVerb")
    verb = UI.Check(tab, LEFT + SUB, y - 24 * row, "с глаголом: «Громмаш говорит: …»", "Вместо двоеточия — что сделал игрок: "
        .. "говорит (/s), кричит (/y), шепчет (шёпот), пишет (остальные каналы), спрашивает (если в строке одни "
        .. "вопросы).", get, set)
    checks[#checks + 1] = verb
    row = row + 1
    get, set = Setting("skipAddons")
    checks[#checks + 1] = UI.Check(tab, LEFT, y - 24 * row, "Не читать сообщения аддонов", "Аддоны других игроков пишут "
        .. "в чат от их имени: Questie — «{звезда} Questie: … 1/1», DBM, BigWigs, Details! и другие. Такие строки "
        .. "не озвучиваются (если в группе у двоих Questie, одно и то же звучало бы дважды); в прозрачном чате "
        .. "они видны, раз их не слышно.", get, set)
    row = row + 1
    if not retail then
        get, set = Setting("waitForCatQuest")
        checks[#checks + 1] = UI.Check(tab, LEFT, y - 24 * row, "Ждать озвучку квестов (CatQuest, Wayfarer)",
            "Пока аддон CatQuest или Wayfarer читает квест, реплику NPC, рассказ о месте или путевую историю, чат "
            .. "замолкает и после дочитывает прерванную строку с начала; ждавшие дольше 40 секунд пропускаются. "
            .. "Без этих аддонов ничего не меняет.", get, set)
        row = row + 1
    end
    y = y - 24 * row - 6

    y = UI.Header(tab, "Каналы", y)
    for i, item in ipairs(CHANNELS) do
        local col, row = (i - 1) % 2, math.floor((i - 1) / 2)
        local get, set = Setting(item[1])
        checks[#checks + 1] = UI.Check(tab, LEFT + col * (RIGHT_COL - LEFT), y - row * 24, ChannelLabel(item), item[5],
            get, set)
    end
    y = y - math.ceil(#CHANNELS / 2) * 24
    -- "Общие каналы" on a row of its own, the channels it holds under it, indented: as the names above
    get, set = Setting("channels", function() Refresh() end)
    checks[#checks + 1] = UI.Check(tab, LEFT, y, "Общие каналы", "Номерные каналы: Общий, Торговля, Поиск спутников, "
        .. "Оборона. Какие из них — галочки под этой.", get, set)
    for i, item in ipairs(NUMBERED) do
        local col, row = (i - 1) % 2, math.floor((i - 1) / 2)
        local g, st = Setting(item[1])
        local c = UI.Check(tab, LEFT + SUB + col * (RIGHT_COL - LEFT - SUB), y - 24 - row * 24, item[2], item[3], g, st)
        checks[#checks + 1] = c
        numbered[#numbered + 1] = c
    end
    y = y - 24 - math.ceil(#NUMBERED / 2) * 24 - 4
    return -y
end

-- "Голоса": the engine, and under it the Windows voices (VoicesWindow.lua).
local function BuildVoices(tab, description)
    local y = Describe(tab, description)
    local voicesLabel = tab:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    voicesLabel:SetPoint("TOPLEFT", LEFT + 4, y - 4)
    voicesLabel:SetText("Голоса:")
    local function Radio(value, label, tip, x)
        local ok, r = pcall(CreateFrame, "CheckButton", nil, tab, "UIRadioButtonTemplate")
        if not ok then r = CreateFrame("CheckButton", nil, tab, "UICheckButtonTemplate") end
        r:SetSize(18, 18)
        r:SetPoint("TOPLEFT", x, y - 2)
        local text = r:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
        text:SetPoint("LEFT", r, "RIGHT", 4, 0)
        text:SetText(label)
        r:SetHitRectInsets(0, -(text:GetStringWidth() + 6), 0, 0)
        r:SetScript("OnClick", function()
            for v, other in pairs(radios) do other:SetChecked(v == value) end
            if ns.db.voices ~= value then ns.SetVoices(value) end
        end)
        UI.Tooltip(r, tip)
        radios[value] = r
    end
    Radio("f5", "Расы", "Голоса рас из русской озвучки самой игры через нейросеть F5-TTS: у каждого персонажа свой голос его "
        .. "расы и пола. Нужна видеокарта с DirectX 12 (проверено пока только на NVIDIA); без неё компаньон читает голосами Windows.", 100)
    Radio("sapi", "Windows", "Русские голоса Windows. Звучат механически — заметно хуже голосов рас, а для разнообразия "
        .. "их нужно искать и ставить отдельно: в Windows по умолчанию только Ирина. Оставлены на всякий случай — если голоса "
        .. "рас отвечают с большой задержкой или не работают на вашем компьютере. Какие раздавать — список ниже.", 190)
    local pane = CreateFrame("Frame", nil, tab)
    pane:SetPoint("TOPLEFT", 0, y - 22 - GAP)
    pane:SetPoint("BOTTOMRIGHT", 0, 0)
    -- the texts and links above the list, then the list at least LIST high
    local LIST = 320
    return -(y - 22 - GAP) + ns.VoicesWindow.Create(pane, TEXT_W) + LIST
end

-- "Помощь": where to write about bugs, ideas and words read wrong.
local MEDIA = "Interface\\AddOns\\BarrensVoice\\Media\\"
local function BuildHelp(tab, description)
    -- three blocks a GAP apart, and the window ending a GAP under the last: the description, the
    -- links, what to send
    local y = Describe(tab, description)
    for i, item in ipairs({ "discord", "telegram", "github" }) do
        local h = UI.LinkRow(tab, LEFT, y, 580 - 2 * LEFT - 4, item, MEDIA .. item)
        y = y - (i < 3 and h or 22)                 -- the last row: its buttons' height, not the row's air
    end
    y = y - GAP
    local _, height = UI.Text(tab, "GameFontHighlight", LEFT + 4, y, TEXT_W,
        "Что прислать: что прозвучало и как надо, а лучше — строку из журнала компаньона (кнопка «Журнал» "
        .. "в окне Barrens Voice). Неверное ударение можно сразу поправить себе на вкладке «Словарь».")
    return -(y - height - (GAP - 8))                -- the tab is 8 px taller than its height (CHROME)
end

-- "Словарь": the editor (DictionaryWindow.lua).
local function BuildDictionary(tab, description)
    local y = Describe(tab, description)
    local pane = CreateFrame("Frame", nil, tab)
    pane:SetPoint("TOPLEFT", 0, y)
    pane:SetPoint("BOTTOMRIGHT", 0, 0)
    ns.DictionaryWindow.Create(pane)
    return 590
end

local function Build()
    window = UI.Window("BarrensVoiceOptions", TITLE, 580, 620)
    local builders = { general = BuildGeneral, reading = BuildReading, voices = BuildVoices,
                       dictionary = BuildDictionary, help = BuildHelp }
    local previous
    for _, item in ipairs(TABS) do
        local key = item[1]
        tabOrder[#tabOrder + 1] = key
        -- the game's own tab, hanging under the window's lower edge
        local ok, button = pcall(CreateFrame, "Button", nil, window, "PanelTabButtonTemplate")
        if ok and button and PanelTemplates_SelectTab and PanelTemplates_DeselectTab then
            button.native = true
            button:SetText(item[2])
            if PanelTemplates_TabResize then PanelTemplates_TabResize(button, 0, nil, 70) end
        else
            button = UI.Button(window, item[2], 120, nil)
        end
        if previous then
            button:SetPoint("TOPLEFT", previous, "TOPRIGHT", 3, 0)
        else
            button:SetPoint("TOPLEFT", window, "BOTTOMLEFT", 11, 2)
        end
        button:SetScript("OnClick", function()
            if PlaySound and SOUNDKIT and SOUNDKIT.IG_CHARACTER_INFO_TAB then PlaySound(SOUNDKIT.IG_CHARACTER_INFO_TAB) end
            Select(key)
        end)
        tabButtons[key], previous = button, button
        local tab = CreateFrame("Frame", nil, window)
        tab:SetPoint("TOPLEFT", 0, -26)
        tab:SetPoint("BOTTOMRIGHT", 0, 6)
        tab:Hide()
        tabs[key] = tab
        tabHeight[key] = builders[key](tab, item[3])
    end
    Select(current)
    window:SetScript("OnShow", function()
        Refresh()
        if C_Timer then C_Timer.After(0, Refresh) end   -- again once the window is laid out
    end)
end

O.Refresh = function() Refresh() end

function O.Toggle()
    if not window then Build() end
    window:SetShown(not window:IsShown())
end

--- The tab shown now (for the tests).
function O.Current()
    return current
end

--- Open the window on the tab `name` ("general", "channels", "reading", "voices", "dictionary").
function O.Open(name)
    if not window then Build() end
    Select(name)
    window:Show()
end

local function RegisterInGameSettings()
    local panel = CreateFrame("Frame")
    panel.name = TITLE
    local title = panel:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
    title:SetPoint("TOPLEFT", 16, -16)
    title:SetText(TITLE)
    local open = UI.Button(panel, "Открыть настройки", 180, function()
        if SettingsPanel and SettingsPanel:IsShown() then pcall(HideUIPanel, SettingsPanel) end
        if not window then Build() end
        window:Show()
    end)
    open:SetPoint("TOPLEFT", title, "BOTTOMLEFT", 0, -12)
    local hint = panel:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
    hint:SetPoint("LEFT", open, "RIGHT", 10, 0)
    hint:SetText("или /bv в чате")
    if Settings and Settings.RegisterCanvasLayoutCategory and Settings.RegisterAddOnCategory then
        Settings.RegisterAddOnCategory(Settings.RegisterCanvasLayoutCategory(panel, panel.name))
    elseif InterfaceOptions_AddCategory then
        InterfaceOptions_AddCategory(panel)
    end
end

function O.Initialize()
    RegisterInGameSettings()
end
