-- Where the strip goes (StripWindow; to the player it is "Мост" - the bridge to the program, a thin
-- dark line the addon talks to the program through, as they may see it): the top edge (default), the bottom edge,
-- or a place of their own - another addon may draw in the same corner (one of its own strips, say).
-- The fields show the top's or the bottom's numbers too, so a place of one's own starts from them.
-- While the window is open an orange frame shows where the line will be; "Сохранить" moves it,
-- telling the program first, "Отмена" leaves it where it is.
local _, ns = ...
local UI = ns.UI

local W = {}
ns.StripWindow = W

local window, screen, from
local radios, fields = {}, {}
local pending = {}

local PLACES = {
    { "top", "Вверху (обычно)" },
    { "bottom", "Внизу" },
    { "custom", "Своё место:" },
}

local function Preview()
    if window and window:IsShown() then
        ns.Strip.Preview(pending.place, pending.x, pending.y, pending.width)
    end
end

local function Refresh()
    if pending.place ~= "custom" then   -- the fields show where the top or bottom line is: a start for one's own
        pending.x, pending.y, pending.width = ns.Strip.Geometry(pending.place)
    end
    for value, r in pairs(radios) do r:SetChecked(pending.place == value) end
    local custom = pending.place == "custom"
    for key, box in pairs(fields) do
        box:SetText(tostring(pending[key] or 0))
        if custom then box:Enable() else box:Disable() end
        box:SetTextColor(custom and 1 or 0.5, custom and 1 or 0.5, custom and 1 or 0.5)
    end
    from:SetChecked(pending.from == "right")
    local physW, physH = GetPhysicalScreenSize()
    local x, y, w, h = ns.Strip.Geometry(pending.place, pending.x, pending.y, pending.width)
    local rows = math.floor(h / ns.db.cell)
    screen:SetText(("Экран %d × %d. Линия: x %d, y %d, ширина %d, толщина %d px (%d %s) — вмещает самую "
        .. "длинную строку чата; чем уже линия, тем она толще."):format(physW, physH, x, y, w, h, rows,
        rows % 10 == 1 and rows % 100 ~= 11 and "ряд" or (rows % 10 >= 2 and rows % 10 <= 4
            and (rows % 100 < 12 or rows % 100 > 14)) and "ряда" or "рядов"))
    Preview()
end

local function Build()
    window = UI.Window("WowChatVoiceStripWindow", "Мост к программе", 400, 300)
    local y = -30
    local note = window:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    note:SetPoint("TOPLEFT", 18, y)
    note:SetWidth(364)
    note:SetJustifyH("LEFT")
    note:SetText("Мост — тонкая тёмная линия у края экрана: через неё аддон передаёт строки чата программе. Если её "
        .. "закрывает другой аддон (рисует что-то в том же месте), перенесите её. Оранжевая рамка показывает, где она будет.")
    UI.TextTooltip(window, note, ns.BRIDGE_TIP)
    y = y - 46

    for i, item in ipairs(PLACES) do
        local value = item[1]
        local ok, r = pcall(CreateFrame, "CheckButton", nil, window, "UIRadioButtonTemplate")
        if not ok then r = CreateFrame("CheckButton", nil, window, "UICheckButtonTemplate") end
        r:SetSize(18, 18)
        r:SetPoint("TOPLEFT", 20, y - (i - 1) * 24)
        local text = r:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
        text:SetPoint("LEFT", r, "RIGHT", 4, 0)
        text:SetText(item[2])
        r:SetHitRectInsets(0, -(text:GetStringWidth() + 6), 0, 0)
        r:SetScript("OnClick", function() W.Pick(value) end)
        radios[value] = r
    end
    y = y - 3 * 24 - 4

    -- x, y, width of the custom place, in physical pixels
    local function Field(key, label, x)
        local text = window:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
        text:SetPoint("TOPLEFT", x, y - 4)
        text:SetText(label)
        local box = CreateFrame("EditBox", nil, window, "InputBoxTemplate")
        box:SetSize(52, 20)
        box:SetPoint("LEFT", text, "RIGHT", 8, 0)
        box:SetAutoFocus(false)
        box:SetNumeric(true)
        box:SetMaxLetters(5)
        box:SetScript("OnTextChanged", function(self, user)
            if not user then return end
            pending[key] = tonumber(self:GetText()) or 0
            Preview()
        end)
        box:SetScript("OnEditFocusLost", function()                      -- show the values as they are kept
            pending.x, pending.y, pending.width = ns.Strip.Geometry("custom", pending.x, pending.y, pending.width)
            Refresh()
        end)
        box:SetScript("OnEnterPressed", function(self) self:ClearFocus() end)
        box:SetScript("OnEscapePressed", function(self) self:ClearFocus() end)
        fields[key] = box
    end
    Field("x", "X", 44)
    Field("y", "Y", 132)
    Field("width", "Ширина", 220)
    y = y - 30

    screen = window:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
    screen:SetPoint("TOPLEFT", 22, y)
    screen:SetWidth(360)
    screen:SetJustifyH("LEFT")
    y = y - 34

    from = UI.Check(window, 18, y, "Рисовать от правого края",
        "Строка рисуется справа налево, от правого края линии. Так короткие строки не дотянутся до того, что "
            .. "может закрывать левую часть линии (например, рисунок другого аддона).",
        function() return pending.from == "right" end,
        function(v) pending.from = v and "right" or "left" end)
    y = y - 34

    local save = UI.Button(window, "Сохранить", 130, function() W.Save() end)
    save:SetPoint("TOPLEFT", 18, y)
    UI.Tooltip(save, "Перенести линию. Программа узнаёт новое место от аддона ещё по старой линии, затем линия переезжает.")
    local cancel = UI.Button(window, "Отмена", 130, function() window:Hide() end)
    cancel:SetPoint("TOPRIGHT", -18, y)
    y = y - 30
    window:SetHeight(-y + 12)

    window:SetScript("OnShow", function()
        pending = { place = ns.db.stripPlace or "top", x = ns.db.stripX or 0, y = ns.db.stripY or 0,
                    width = ns.db.stripWidth or 800, from = ns.db.stripFrom or "left" }
        Refresh()
    end)
    window:SetScript("OnHide", function() ns.Strip.Preview(nil) end)
end

--- Choose a place in the window (its radio buttons): the top's or bottom's numbers stay in the
--- fields when "custom" is chosen next.
function W.Pick(place)
    pending.place = place
    Refresh()
end

--- Keep the place being edited and move the line there.
function W.Save()
    local x, y, w = ns.Strip.Geometry(pending.place, pending.x, pending.y, pending.width)
    ns.db.stripPlace, ns.db.stripFrom = pending.place, pending.from
    if pending.place == "custom" then
        ns.db.stripX, ns.db.stripY, ns.db.stripWidth = x, y, w
    end
    ns.Strip.MoveTo()
    window:Hide()
end

--- The place being edited (for the tests).
function W.Pending()
    return pending
end

function W.Toggle()
    if not window then Build() end
    window:SetShown(not window:IsShown())
end
