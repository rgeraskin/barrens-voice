-- The minimap button (as CatQuest's: on the minimap ring, dragged around it) and the entry in the
-- client's addon compartment. Left click: the settings window; right click: reading on/off; the mouse wheel over
-- the button: the volume, as the slider on «Общее» (each line carries it to the launcher: the next one sounds so).
local _, ns = ...

local M = {}
ns.Minimap = M

local ICON = "Interface\\AddOns\\BarrensVoice\\Icon"
local button, icon

M.VOLUME_STEP = 10          -- percent a notch of the wheel; the slider's range, 0..200
M.VOLUME_MAX = 200

--- One notch of the wheel (+1 up: louder, -1 down: quieter): the volume setting moved within its range, and the
--- slider in the settings follows. The new volume.
function M.Wheel(delta)
    local now = tonumber(ns.db.volume) or 100
    local value = math.max(0, math.min(M.VOLUME_MAX, now + (delta > 0 and 1 or -1) * M.VOLUME_STEP))
    ns.db.volume = value
    if ns.Options.Refresh then ns.Options.Refresh() end
    return value
end

local function Position()
    local angle = math.rad(ns.db.minimapAngle or 160)
    local radius = Minimap:GetWidth() / 2 + 5
    button:ClearAllPoints()
    button:SetPoint("CENTER", Minimap, "CENTER", math.cos(angle) * radius, math.sin(angle) * radius)
end

local function ShowTooltip(self)
    GameTooltip:SetOwner(self, "ANCHOR_LEFT")
    GameTooltip:AddLine("Barrens Voice")
    GameTooltip:AddLine(ns.db.enabled and "|cff40ff40Озвучка чата включена|r" or "|cffff4040Озвучка чата выключена|r")
    GameTooltip:AddLine(("Громкость: |cffffd100%d%%|r"):format(tonumber(ns.db.volume) or 100))
    GameTooltip:AddLine("ЛКМ — настройки", 1, 1, 1)
    GameTooltip:AddLine("ПКМ — включить или выключить (выключение сразу обрывает фразу)", 1, 1, 1)
    GameTooltip:AddLine("Колёсико — тише или громче", 1, 1, 1)
    GameTooltip:AddLine("Перетащи, чтобы передвинуть", 0.6, 0.6, 0.6)
    GameTooltip:Show()
end

function M.Refresh()
    if icon then icon:SetDesaturated(not ns.db.enabled) end
end

function M.ToggleEnabled()
    ns.SetEnabled(not ns.db.enabled)
end

local function Create()
    button = CreateFrame("Button", "BarrensVoiceMinimapButton", Minimap)
    button:SetSize(31, 31)
    button:SetFrameStrata("MEDIUM")
    button:SetFrameLevel(8)
    button:RegisterForClicks("LeftButtonUp", "RightButtonUp")
    button:RegisterForDrag("LeftButton")
    button:SetHighlightTexture("Interface\\Minimap\\UI-Minimap-ZoomButton-Highlight")
    local border = button:CreateTexture(nil, "OVERLAY")
    border:SetSize(50, 50)
    border:SetTexture("Interface\\Minimap\\MiniMap-TrackingBorder")
    border:SetPoint("TOPLEFT")
    local bg = button:CreateTexture(nil, "BACKGROUND")
    bg:SetSize(24, 24)
    bg:SetTexture("Interface\\Minimap\\UI-Minimap-Background")
    bg:SetPoint("CENTER", 0, 1)
    icon = button:CreateTexture(nil, "ARTWORK")
    icon:SetSize(18, 18)
    icon:SetTexture(ICON)
    icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
    icon:SetPoint("CENTER", 0, 1)

    button:SetScript("OnClick", function(self, which)
        if which == "RightButton" then
            M.ToggleEnabled()
        else
            ns.Options.Toggle()
        end
        if self:IsMouseOver() then ShowTooltip(self) end
    end)
    button:EnableMouseWheel(true)
    button:SetScript("OnMouseWheel", function(self, delta)
        M.Wheel(delta)
        if self:IsMouseOver() then ShowTooltip(self) end    -- the new volume in the tooltip at once
    end)
    button:SetScript("OnEnter", ShowTooltip)
    button:SetScript("OnLeave", GameTooltip_Hide)
    button:SetScript("OnDragStart", function(self)
        GameTooltip_Hide()
        self:SetScript("OnUpdate", function()
            local mx, my = Minimap:GetCenter()
            local cx, cy = GetCursorPosition()
            local scale = Minimap:GetEffectiveScale()
            ns.db.minimapAngle = math.deg(math.atan2(cy / scale - my, cx / scale - mx))
            Position()
        end)
    end)
    button:SetScript("OnDragStop", function(self) self:SetScript("OnUpdate", nil) end)
    Position()
    M.Refresh()
end

function M.Update()
    if ns.db.minimapIcon and not button then Create() end
    if button then button:SetShown(ns.db.minimapIcon and true or false) end
end

-- The client's addon compartment (the button by the minimap that lists addons); named in the .toc.
function BarrensVoice_OnCompartmentClick(_, which)
    if which == "RightButton" then M.ToggleEnabled() else ns.Options.Toggle() end
end
