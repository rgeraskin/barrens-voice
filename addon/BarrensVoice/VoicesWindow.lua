-- "Голоса Windows": which of the program's Windows voices characters get, each with a play button,
-- a filter (name, engine or sex: "silero", "edge", "жен") and on/off for all the voices shown. It
-- fills a pane of the settings window (the "Голоса" tab, Options.lua).
-- The list comes from VoiceList.lua, which the program writes (WoW reads it at start and /reload).
local _, ns = ...
local UI = ns.UI

local V = {}
ns.VoicesWindow = V

local ROW = 24
local window, content, filter, count, empty
local rows = {}

local function List()
    return BarrensVoiceVoiceList or {}
end

local function IsOn(entry)
    if ns.db.voiceOff then return not ns.db.voiceOff[entry.name] end
    return entry.on ~= false
end

--- The first change here makes the program's defaults the addon's own list.
local function SetOn(entry, on)
    if not ns.db.voiceOff then
        ns.db.voiceOff = {}
        for _, e in ipairs(List()) do
            if e.on == false then ns.db.voiceOff[e.name] = true end
        end
    end
    ns.db.voiceOff[entry.name] = (not on) and true or nil
end

local function GenderText(entry)
    return entry.gender == "Male" and "муж." or entry.gender == "Female" and "жен." or ""
end

local function Matches(entry, text)
    if text == "" then return true end
    local haystack = ns.Dictionary.Norm((entry.label or entry.name) .. " " .. GenderText(entry))
    return haystack:find(ns.Dictionary.Norm(text), 1, true) ~= nil
end

local function Shown()
    local text = filter and filter:GetText() or ""
    local out = {}
    for _, entry in ipairs(List()) do
        if Matches(entry, text) then out[#out + 1] = entry end
    end
    return out
end

local function Refresh()
    local list, shown = List(), Shown()
    empty:SetShown(#list == 0)
    local on = 0
    for _, e in ipairs(list) do if IsOn(e) then on = on + 1 end end
    count:SetText(#list > 0 and ("включено %d из %d"):format(on, #list) or "")
    for i, entry in ipairs(shown) do
        local row = rows[i]
        row.entry = entry
        row.check:SetChecked(IsOn(entry))
        row.text:SetText(entry.label or entry.name)
        row.gender:SetText(GenderText(entry))
        row:Show()
    end
    for i = #shown + 1, #rows do rows[i]:Hide() end
    content:SetHeight(math.max(10, #shown * ROW))
end

local function SetAllShown(on)
    for _, entry in ipairs(Shown()) do SetOn(entry, on) end
    ns.SendControl()
    Refresh()
end

--- Build the list into `pane` (a frame the size of the tab), its texts `width` wide; returns the height
--- of what is above the list (the list takes the rest of the pane).
function V.Create(pane, width)
    window = pane
    width = width or 536
    local GAP = 14

    local _, h = UI.Text(window, "GameFontHighlight", 22, 0, width,
        "Голоса Windows звучат механически, заметно хуже голосов рас, а для разнообразия их нужно ставить "
        .. "отдельно (в Windows по умолчанию только Ирина). Они оставлены на всякий случай — если голоса рас отвечают "
        .. "с большой задержкой или не работают на твоём компьютере.\n\nВыбранные голоса раздаются игрокам по имени и полу.")
    local y = -h - GAP

    -- where to get more voices: the address to copy, and «Копировать» / «Открыть» (UI.LinkRow)
    local _, eh = UI.Text(window, "GameFontHighlight", 22, y, width, "Скачать дополнительные голоса можно, например, здесь:")
    y = y - eh - 6
    for _, key in ipairs({ "rhvoice", "silero" }) do
        y = y - UI.LinkRow(window, 22, y, 580 - 44, key)
    end
    y = y + 4 - GAP                                   -- the last row's air, then the gap

    filter = CreateFrame("EditBox", nil, window, "InputBoxTemplate")
    filter:SetHeight(20)
    filter:SetPoint("TOPLEFT", 24, y)
    filter:SetWidth(170)
    filter:SetAutoFocus(false)
    local placeholder = filter:CreateFontString(nil, "OVERLAY", "GameFontDisable")
    placeholder:SetPoint("LEFT", 2, 0)
    placeholder:SetText("фильтр: silero, edge, жен…")
    filter:SetScript("OnTextChanged", function(self)
        placeholder:SetShown(self:GetText() == "")
        Refresh()
    end)
    filter:SetScript("OnEscapePressed", function(self)
        self:SetText("")
        self:ClearFocus()
    end)
    UI.Tooltip(filter, "Показать голоса, в названии которых есть этот текст: имя, движок (RHVoice, Silero, Edge) "
        .. "или пол (муж., жен.).\n\n«Вкл. все» и «Выкл. все» действуют на показанные.")
    local allOn = UI.Button(window, "Вкл. все", 82, function() SetAllShown(true) end)
    allOn:SetPoint("LEFT", filter, "RIGHT", 10, 0)
    local allOff = UI.Button(window, "Выкл. все", 82, function() SetAllShown(false) end)
    allOff:SetPoint("LEFT", allOn, "RIGHT", 4, 0)
    -- what «>» in a row does: on the filter row, at the right, over the rows' «>» (their right edge: the list's
    -- frame 14 in from the pane's, the scroll bar's 28, the row's 6 - 48 from the pane's edge)
    local listen = window:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    listen:SetPoint("RIGHT", window, "TOPRIGHT", -48, y - 10)
    listen:SetText("«>» — послушать.")

    local box = UI.Box(window)
    box:SetPoint("TOPLEFT", 14, y - 28)
    box:SetPoint("BOTTOMRIGHT", -14, 30)
    local scroll = CreateFrame("ScrollFrame", nil, box, "UIPanelScrollFrameTemplate")
    scroll:SetPoint("TOPLEFT", 8, -8)
    scroll:SetPoint("BOTTOMRIGHT", -28, 8)
    content = CreateFrame("Frame", nil, scroll)
    content:SetSize(516, 10)                    -- the scroll area's width (580 - 2 * 14 - 8 - 28); kept in step below
    scroll:SetScrollChild(content)
    scroll:SetScript("OnSizeChanged", function(_, w) if w and w > 0 then content:SetWidth(w) end end)

    for i = 1, #List() do
        local row = CreateFrame("Frame", nil, content)
        row:SetHeight(ROW)
        row:SetPoint("TOPLEFT", 0, -(i - 1) * ROW)
        row:SetPoint("RIGHT", content, "RIGHT", -6, 0)   -- sex and «>» at the right edge, by the scroll bar
        row.check = CreateFrame("CheckButton", nil, row, "UICheckButtonTemplate")
        row.check:SetSize(22, 22)
        row.check:SetPoint("LEFT", 0, 0)
        row.check:SetScript("OnClick", function(self)
            SetOn(row.entry, self:GetChecked())
            ns.SendControl()
            Refresh()
        end)
        row.text = row:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
        row.text:SetPoint("LEFT", row.check, "RIGHT", 4, 0)
        row.gender = row:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
        row.gender:SetPoint("RIGHT", -34, 0)
        row.play = UI.Button(row, ">", 26, function() ns.TestVoice(row.entry.name) end)
        row.play:SetHeight(20)
        row.play:SetPoint("RIGHT", 0, 0)
        rows[i] = row
    end

    count = window:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
    count:SetPoint("BOTTOMLEFT", 20, 10)

    empty = window:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    empty:SetPoint("CENTER")
    empty:SetWidth(420)
    empty:SetText("Список пуст: запусти Barrens Voice Launcher (он запишет голоса в аддон) и сделай /reload.")

    window:SetScript("OnShow", Refresh)
    return -(y - 28)
end


