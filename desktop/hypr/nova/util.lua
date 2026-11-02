-- Nova OS — fonctions utilitaires pour la configuration Hyprland (Lua).
local M = {}

function M.read_file(path)
  local f = io.open(path, "r")
  if not f then return nil end
  local content = f:read("*a")
  f:close()
  return content
end

function M.file_exists(path)
  local f = io.open(path, "r")
  if f then
    f:close()
    return true
  end
  return false
end

local function is_list(t)
  if type(t) ~= "table" then return false end
  local count = 0
  for _ in pairs(t) do count = count + 1 end
  return count > 0 and count == #t
end

-- Fusion récursive : les valeurs de `over` remplacent celles de `base`.
-- Les listes (et les tables vides) sont remplacées en bloc, pas fusionnées.
function M.merge(base, over)
  local out = {}
  for k, v in pairs(base or {}) do
    out[k] = (type(v) == "table") and M.merge(v, nil) or v
  end
  for k, v in pairs(over or {}) do
    if type(v) == "table" and next(v) ~= nil and not is_list(v) and type(out[k]) == "table" and not is_list(out[k]) then
      out[k] = M.merge(out[k], v)
    else
      out[k] = v
    end
  end
  return out
end

-- Correspondance des cartes clavier console (vconsole) vers XKB.
local VCONSOLE_TO_XKB = {
  ["fr"] = { "fr", "" }, ["fr-latin1"] = { "fr", "" }, ["fr-latin9"] = { "fr", "" },
  ["fr-pc"] = { "fr", "" }, ["fr-bepo"] = { "fr", "bepo" }, ["fr-bepo-latin9"] = { "fr", "bepo" },
  ["be-latin1"] = { "be", "" }, ["fr_CH"] = { "ch", "fr" }, ["fr_CH-latin1"] = { "ch", "fr" },
  ["cf"] = { "ca", "fr" }, ["us"] = { "us", "" }, ["uk"] = { "gb", "" },
  ["de"] = { "de", "" }, ["de-latin1"] = { "de", "" }, ["es"] = { "es", "" }, ["it"] = { "it", "" },
}

-- Disposition clavier du système (réglée par l'installateur via localectl).
-- Retourne layout, variant, options. Défaut : AZERTY français.
function M.system_keyboard()
  local x11 = M.read_file("/etc/X11/xorg.conf.d/00-keyboard.conf")
  if x11 then
    local layout = x11:match('Option%s+"XkbLayout"%s+"([^"]+)"')
    if layout then
      local variant = x11:match('Option%s+"XkbVariant"%s+"([^"]*)"') or ""
      local options = x11:match('Option%s+"XkbOptions"%s+"([^"]*)"') or ""
      return layout, variant, options
    end
  end
  local vconsole = M.read_file("/etc/vconsole.conf")
  local keymap = vconsole and vconsole:match("KEYMAP=([%w%-_]+)")
  if keymap then
    local known = VCONSOLE_TO_XKB[keymap]
    if known then return known[1], known[2], "" end
    return keymap:match("^(%a+)") or "fr", "", ""
  end
  return "fr", "", ""
end

-- Vrai si la machine est sur secteur (ou n'a pas de batterie).
function M.on_ac_power()
  local has_battery = false
  local ok, pipe = pcall(io.popen, "ls /sys/class/power_supply 2>/dev/null")
  if not ok or not pipe then return true end
  for name in pipe:lines() do
    local base = "/sys/class/power_supply/" .. name
    local kind = (M.read_file(base .. "/type") or ""):gsub("%s+", "")
    if kind == "Mains" or kind == "USB" then
      if (M.read_file(base .. "/online") or ""):match("1") then
        pipe:close()
        return true
      end
    elseif kind == "Battery" then
      has_battery = true
    end
  end
  pipe:close()
  return not has_battery
end

-- Premier chemin existant parmi une liste (thèmes de curseur, etc.).
function M.first_existing(paths, fallback)
  for _, candidate in ipairs(paths) do
    if M.file_exists(candidate.check) then return candidate.value end
  end
  return fallback
end

return M
