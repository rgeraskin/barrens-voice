-- Small building blocks shared by the addon's windows, so they look alike.
local _, ns = ...

local UI = {}
ns.UI = UI

UI.GOLD = { 1, 0.82, 0 }

function UI.Tooltip(widget, text)
    widget:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        GameTooltip:SetText(type(text) == "function" and text() or text, 1, 1, 1, 1, true)
        GameTooltip:Show()
    end)
    widget:SetScript("OnLeave", GameTooltip_Hide)
end

--- A movable window with a title that closes on Escape.
function UI.Window(name, title, width, height, strata)
    local w = CreateFrame("Frame", name, UIParent, "BasicFrameTemplateWithInset")
    w:SetSize(width, height)
    w:SetPoint("CENTER")
    w:SetFrameStrata(strata or "DIALOG")
    w:SetToplevel(true)
    w:SetMovable(true)
    w:EnableMouse(true)
    w:RegisterForDrag("LeftButton")
    w:SetScript("OnDragStart", w.StartMoving)
    w:SetScript("OnDragStop", w.StopMovingOrSizing)
    w:SetClampedToScreen(true)
    w:Hide()
    tinsert(UISpecialFrames, name)
    local t = w:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    t:SetPoint("TOP", 0, -5)
    t:SetText(title)
    w.title = t
    return w
end

--- A block of text `width` wide from (x, y), wrapped; returns it and its height - so what comes below
--- starts under its last line, however many lines the text took (FontString:GetStringHeight).
function UI.Text(parent, font, x, y, width, text)
    local s = parent:CreateFontString(nil, "OVERLAY", font)
    s:SetPoint("TOPLEFT", x, y)
    s:SetWidth(width)
    s:SetJustifyH("LEFT")
    s:SetText(text)
    return s, s:GetStringHeight() or 12
end

--- A section title in gold with a thin rule to the right edge; returns the y below it.
function UI.Header(parent, text, y)
    local label = parent:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    label:SetPoint("TOPLEFT", 18, y)
    label:SetText(text)
    local rule = parent:CreateTexture(nil, "ARTWORK")
    rule:SetColorTexture(UI.GOLD[1], UI.GOLD[2], UI.GOLD[3], 0.25)
    rule:SetHeight(1)
    rule:SetPoint("LEFT", label, "RIGHT", 8, 0)
    rule:SetPoint("RIGHT", parent, "RIGHT", -18, 0)
    return y - 22
end

--- A check box with a label; `get`/`set` read and write the setting.
function UI.Check(parent, x, y, label, tip, get, set)
    local c = CreateFrame("CheckButton", nil, parent, "UICheckButtonTemplate")
    c:SetSize(24, 24)
    c:SetPoint("TOPLEFT", x, y)
    local text = c:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    text:SetPoint("LEFT", c, "RIGHT", 2, 0)
    text:SetText(label)
    c.label = text
    c:SetHitRectInsets(0, -(text:GetStringWidth() + 6), 0, 0)
    c:SetScript("OnClick", function(self) set(self:GetChecked() and true or false) end)
    c.refresh = function() c:SetChecked(get() and true or false) end
    if tip then UI.Tooltip(c, tip) end
    return c
end

--- A tooltip over a text (a font string has none of its own): an invisible frame on top of it.
function UI.TextTooltip(parent, fontString, text)
    local f = CreateFrame("Frame", nil, parent)
    f:SetAllPoints(fontString)
    f:EnableMouse(true)
    UI.Tooltip(f, text)
    return f
end

function UI.SetCheckEnabled(c, enabled)
    if enabled then c:Enable() else c:Disable() end
    c.label:SetTextColor(enabled and 1 or 0.5, enabled and 1 or 0.5, enabled and 1 or 0.5)
end

function UI.Button(parent, text, width, onClick)
    local b = CreateFrame("Button", nil, parent, "UIPanelButtonTemplate")
    b:SetSize(width, 22)
    b:SetText(text)
    b:SetScript("OnClick", onClick)
    return b
end

--- A page to visit (one of ns.LINKS): an icon if given, its name, the address in a box (a click selects
--- it, Ctrl+C copies it; typing does not change it), and «Копировать» and «Открыть», which the companion
--- does (Core.lua ns.CopyLink, ns.OpenLink). `width` from `x` to the last button. Returns the row's height.
function UI.LinkRow(parent, x, y, width, key, icon)
    local link = ns.LINKS[key]
    local left = x
    if icon then
        local t = parent:CreateTexture(nil, "ARTWORK")
        t:SetSize(20, 20)
        t:SetPoint("TOPLEFT", x, y)
        t:SetTexture(icon)
        left = x + 26
    end
    local name = parent:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    name:SetPoint("TOPLEFT", left, y - 4)
    name:SetWidth(70)
    name:SetJustifyH("LEFT")
    name:SetText(link[1])
    local open = UI.Button(parent, "Открыть", 76, function() ns.OpenLink(key) end)
    open:SetPoint("TOPLEFT", x + width - 76, y)
    UI.Tooltip(open, "Компаньон откроет страницу в браузере: аддону игра браузер не даёт.")
    local copy = UI.Button(parent, "Копировать", 96, function() ns.CopyLink(key) end)
    copy:SetPoint("RIGHT", open, "LEFT", -4, 0)
    UI.Tooltip(copy, "Компаньон положит адрес в буфер обмена: аддону игра буфер обмена не даёт. Без компаньона — щёлкните по адресу и нажмите Ctrl+C.")
    local box = CreateFrame("EditBox", nil, parent, "InputBoxTemplate")
    box:SetHeight(20)
    box:SetAutoFocus(false)
    box:SetPoint("LEFT", name, "RIGHT", 8, 0)
    box:SetPoint("RIGHT", copy, "LEFT", -10, 0)
    box:SetText(link[2])
    box:SetCursorPosition(0)
    box:SetScript("OnTextChanged", function(self, user)
        if user then self:SetText(link[2]); self:HighlightText() end
    end)
    box:SetScript("OnEditFocusGained", function(self) self:HighlightText() end)
    box:SetScript("OnMouseUp", function(self) self:SetFocus(); self:HighlightText() end)
    box:SetScript("OnEscapePressed", function(self) self:ClearFocus() end)
    box:SetScript("OnEnterPressed", function(self) self:ClearFocus() end)
    UI.Tooltip(box, "Щелчок выделяет адрес, Ctrl+C копирует.")
    return 26
end

--- A dark box with a border, for text fields (falls back to a plain dark panel without
--- BackdropTemplate).
function UI.Box(parent)
    local box
    if BackdropTemplateMixin then
        box = CreateFrame("Frame", nil, parent, "BackdropTemplate")
        box:SetBackdrop({
            bgFile = "Interface\\Tooltips\\UI-Tooltip-Background",
            edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
            tile = true, tileSize = 16, edgeSize = 14,
            insets = { left = 4, right = 4, top = 4, bottom = 4 },
        })
        box:SetBackdropColor(0, 0, 0, 0.75)
        box:SetBackdropBorderColor(0.6, 0.6, 0.6, 1)
    else
        box = CreateFrame("Frame", nil, parent)
        local bg = box:CreateTexture(nil, "BACKGROUND")
        bg:SetAllPoints()
        bg:SetColorTexture(0, 0, 0, 0.75)
    end
    return box
end
