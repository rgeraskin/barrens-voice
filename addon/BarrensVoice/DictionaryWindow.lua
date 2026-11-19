-- The slang dictionary (the "Словарь" tab of the settings window, Options.lua): the text in a framed
-- box with padding, the "?" help, back to the default and a line to try.
local _, ns = ...
local UI = ns.UI

local W = {}
ns.DictionaryWindow = W

-- The help ("?"): every kind of entry and a short regular expression cheat sheet.
local HELP = {
    "|cffffd100Простые записи|r",
    "|cffffd100WTS=продам|r — слово. Регистр и ё/е не важны",
    "|cffffd100мертвые копи=мёртвые к+опи|r — фраза из нескольких слов",
    "|cffffd100дамагер*=дам+агер*|r — основа со звёздочкой:",
    "     «дамагера» прочитается как «дам+агера»",
    "|cffffd100+|r перед гласной — ударение",
    "|cffffd100!|r в начале замены — не склонять её после предлога:",
    "     |cffffd100скачки=!ск+ачки|r: «после скачки» не станет «после скачек»",
    "Пустая замена удаляет слово, |cffffd100#|r в начале строки — комментарий.",
    "После правки записи сами выстраиваются по алфавиту:",
    "     сначала русские, потом латиница и цифры, регулярки — в конце.",
    "",
    "|cffffd100Регулярные выражения|r",
    "Строка |cffffd100~регулярка=замена|r. Это Python, без учёта регистра.",
    "Шаблон от замены отделяет последний «=».",
    "Применяет их лаунчер: аддон передаёт их ему сразу после правки.",
    "",
    "|cffffd100Знаки в регулярках|r",
    "|cffffd100\\d|r цифра,   |cffffd100\\w|r буква или цифра,   |cffffd100\\s|r пробел,   |cffffd100.|r любой символ",
    "|cffffd100+|r один или больше,   |cffffd100*|r ноль или больше,   |cffffd100?|r необязательно",
    "|cffffd100{2,3}|r от 2 до 3 раз,   |cffffd100\\b|r граница слова,   |cffffd100^ $|r начало и конец строки",
    "|cffffd100а||б|r или,   |cffffd100[абв]|r один из,   |cffffd100[^0-9]|r любой, кроме цифр",
    "|cffffd100( )|r группа, в замене |cffffd100\\1|r или |cffffd100\\g<1>|r — её текст",
    "",
    "|cffffd100Примеры|r",
    "|cffffd100~(\\d+)\\s*к\\b=\\g<1>000|r",
    "     «5к» прочитается как «5000» — «пять тысяч»",
    "|cffffd100~\\bго+\\b=го|r",
    "     «гоооо» прочитается как «го»",
    "|cffffd100~(ха){3,}=смеётся|r",
    "     «хахахаха» прочитается как «смеётся»",
    "|cffffd100~\\b(\\d+)\\s*дд\\b=\\1 [дамагер||дамагера||дамагеров]|r",
    "     «2дд» прочитается как «2 дамагера». В [ ] три формы слова:",
    "     после 1, после 2-4 и после 5 и больше. Нужная выберется по числу.",
    "|cffffd100~\\b(\\d+)\\s*лвл\\b=<\\1> уровень|r",
    "     «60 лвл» прочитается как «шестидесятый уровень»: <\\1> — число словом, порядковое.",
    "     После предлога склоняется: «до 60 лвл» — «до шестидесятого уровня».",
}

function W.HelpTooltip(widget)
    widget:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        GameTooltip:AddLine("Словарь сленга", 1, 1, 1)
        GameTooltip:AddLine(" ")
        for _, line in ipairs(HELP) do
            if line == "" then GameTooltip:AddLine(" ") else GameTooltip:AddLine(line, 0.9, 0.9, 0.9) end
        end
        GameTooltip:Show()
    end)
    widget:SetScript("OnLeave", GameTooltip_Hide)
end

local window, edit

local function Save(text)
    ns.Dictionary.SetText(text)          -- kept as edits of the default (Dictionary.lua, layers)
end

--- Build the dictionary into `pane` (a frame the size of the tab).
function W.Create(pane)
    window = pane

    -- The short rules as a list; the rest is behind "?".
    local RULES = {
        "Одна строка — одна запись: |cffffd100ключ=как читать|r (WTS=продам)",
        "Регистр и ё/е не важны",
        "После правки записи сами выстраиваются по алфавиту, регулярки — в конце",
        "Ударение — |cffffd100+|r перед гласной: дам+агер",
        "Строки с |cffffd100~|r — регулярные выражения, их применяет лаунчер",
        "Подробности и примеры — кнопка |cffffd100?|r справа",
    }
    local y = -6
    for _, rule in ipairs(RULES) do
        local line = window:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
        line:SetPoint("TOPLEFT", 20, y)
        line:SetPoint("RIGHT", -52, 0)
        line:SetJustifyH("LEFT")
        line:SetText("|cffffd100-|r  " .. rule)
        y = y - 18
    end
    local help = UI.Button(window, "?", 26, nil)
    help:SetPoint("TOPRIGHT", -18, -4)
    W.HelpTooltip(help)

    -- The text in a framed box, with padding inside.
    local box = UI.Box(window)
    box:SetPoint("TOPLEFT", 14, y - 8)
    box:SetPoint("BOTTOMRIGHT", -14, 54)
    local scroll = CreateFrame("ScrollFrame", "BarrensVoiceDictionaryScroll", box, "UIPanelScrollFrameTemplate")
    scroll:SetPoint("TOPLEFT", 10, -10)
    scroll:SetPoint("BOTTOMRIGHT", -30, 10)
    edit = CreateFrame("EditBox", nil, scroll)
    edit:SetMultiLine(true)
    edit:SetAutoFocus(false)
    edit:SetMaxLetters(0)
    edit:SetFontObject(ChatFontNormal)
    edit:SetTextInsets(4, 4, 2, 2)
    edit:SetWidth(480)
    edit:SetScript("OnEscapePressed", edit.ClearFocus)
    -- the box holds every "|" as "||" (Dictionary.lua D.Escaped): out of it unescaped, into it escaped
    edit:SetScript("OnTextChanged", function(self, userInput)
        if not userInput then return end
        ns.Dictionary.SetText(ns.Dictionary.Unescaped(self:GetText()))
    end)
    -- Sorted when editing is done, not while typing (the cursor would jump).
    edit:SetScript("OnEditFocusLost", function(self)
        Save(ns.Dictionary.Unescaped(self:GetText()))
        local text = ns.Dictionary.Escaped(ns.Dictionary.Text())
        if self:GetText() ~= text then self:SetText(text) end
    end)
    scroll:SetScrollChild(edit)
    scroll:SetScript("OnSizeChanged", function(_, w) edit:SetWidth(w) end)
    box:EnableMouse(true)
    box:SetScript("OnMouseDown", function() edit:SetFocus() end)

    local reset = UI.Button(window, "Сбросить словарь", 170, function()
        ns.Dictionary.Reset()
        edit:SetText(ns.Dictionary.Escaped(ns.Dictionary.Text()))
    end)
    reset:SetPoint("BOTTOMRIGHT", -16, 20)
    UI.Tooltip(reset, "Вернуть стандартный словарь аддона.\n\nТвои записи и правки пропадут.")
    local try = CreateFrame("EditBox", nil, window, "InputBoxTemplate")
    try:SetHeight(20)
    try:SetPoint("BOTTOMLEFT", 24, 22)
    try:SetPoint("BOTTOMRIGHT", -296, 22)
    try:SetAutoFocus(false)
    try:SetText("WTS сумки, нужен дд в ОП")
    local function Say()
        if ns.Off() then return end
        local _, class = UnitClass("player")
        local _, race = UnitRace("player")
        -- an edit of the last 2 s is still waiting to be sent (Core.lua ns.DictionaryChanged): it goes
        -- first, so the line is read with the dictionary as it is now
        ns.SendDictionary(false)
        ns.Send("test", UnitName("player"), race, UnitSex("player"), class, "", try:GetText())
        try:ClearFocus()
    end
    try:SetScript("OnEnterPressed", Say)
    local say = UI.Button(window, "Озвучить", 96, Say)
    say:SetPoint("LEFT", try, "RIGHT", 8, 0)
    UI.Tooltip(say, "Прочитать строку слева твоим голосом — со словарём и регулярками.")

    window:SetScript("OnShow", function()
        edit:SetText(ns.Dictionary.Escaped(ns.Dictionary.Text()))
    end)
end


