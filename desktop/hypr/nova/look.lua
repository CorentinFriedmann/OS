-- Nova OS — apparence : verre minimaliste (flou dépoli, bordures fines, ombres douces).
--
-- Effets « intelligents » : sur batterie (ou en mode éco / jeu), les effets
-- coûteux sont réduits automatiquement pour économiser l'énergie et les FPS.
-- Le mode est piloté par nova-mode via le fichier $XDG_RUNTIME_DIR/nova/visual-mode
-- (valeurs : auto | full | eco | game).
local util = require("nova.util")
local M = {}

-- Palette « Nova Verre » (branding/palette.json)
local STYLE = {
  border = { colors = { "rgba(c3d6ff8c)", "rgba(8ab4ff73)", "rgba(b9adff66)" }, angle = 135 },
  border_inactive = "rgba(ffffff14)",
  glow = { colors = { "rgba(8ab4ff40)", "rgba(b9adff33)" }, angle = 135 },
}

local function visual_mode_file()
  local runtime = os.getenv("XDG_RUNTIME_DIR") or "/tmp"
  return runtime .. "/nova/visual-mode"
end

-- Détermine le niveau d'effets à appliquer : "full", "eco" ou "game".
local function current_level(look)
  local forced = util.read_file(visual_mode_file())
  forced = forced and forced:gsub("%s+", "") or "auto"
  if forced == "full" or forced == "eco" or forced == "game" then return forced end
  if look.power_aware and not util.on_ac_power() then return "eco" end
  return "full"
end

local function apply_level(look, level)
  local fancy = level == "full"
  local playing = level == "game"
  hl.config({
    general = {
      allow_tearing = playing,
      col = { active_border = STYLE.border, inactive_border = STYLE.border_inactive },
    },
    decoration = {
      shadow = {
        enabled = look.shadow and fancy,
        range = 32,
        render_power = 2,
        offset = "0 6",
        color = "rgba(0000008c)",
        color_inactive = "rgba(00000047)",
      },
      glow = {
        enabled = look.glow and not playing,
        range = fancy and 12 or 6,
        render_power = 3,
        color = STYLE.glow,
        color_inactive = "rgba(00000000)",
      },
      blur = {
        enabled = look.blur and not playing,
        size = fancy and 10 or 5,
        passes = fancy and 3 or 1,
        noise = 0.02,
        contrast = 0.9,
        brightness = 0.82,
        vibrancy = 0.15,
        vibrancy_darkness = 0.2,
        popups = true,
        special = fancy,
      },
    },
    animations = { enabled = look.animations and not playing },
  })
  hl.animation({
    leaf = "borderangle",
    enabled = look.border_animation and fancy,
    speed = 80,
    bezier = "linear",
    style = "loop",
  })
end

function M.apply(cfg)
  local look = cfg.look

  -- Échelle automatique, sauf en machine virtuelle : l'écran virtuel n'annonce pas sa
  -- taille physique et Hyprland grossirait tout ×2 (bureau minuscule, barre tronquée).
  local scale = util.virtual_machine() and 1 or "auto"
  hl.monitor({ output = "", mode = "preferred", position = "auto", scale = scale })

  hl.config({
    general = {
      gaps_in = look.gaps_in,
      gaps_out = look.gaps_out,
      border_size = look.border_size,
      layout = "dwindle",
      resize_on_border = true,
      snap = { enabled = true, window_gap = 12, monitor_gap = 12 },
    },
    decoration = {
      rounding = look.rounding,
      rounding_power = 2.5,
      active_opacity = 1.0,
      inactive_opacity = look.inactive_opacity,
      fullscreen_opacity = 1.0,
      dim_special = 0.35,
    },
    dwindle = { preserve_split = true },
    misc = {
      disable_hyprland_logo = true,
      disable_splash_rendering = true,
      force_default_wallpaper = 0,
      background_color = "rgb(0b0d12)",
      focus_on_activate = true,
      mouse_move_enables_dpms = true,
      key_press_enables_dpms = true,
      vrr = 2,
      font_family = "Inter",
    },
    ecosystem = { no_update_news = true, no_donation_nag = true },
  })

  -- Courbes : fluides et posées, sans rebond (décélération douce)
  hl.curve("nova",       { type = "bezier", points = { { 0.22, 1 },  { 0.36, 1 } } })
  hl.curve("novaOut",    { type = "bezier", points = { { 0.55, 0 },  { 1, 0.45 } } })
  hl.curve("smooth",     { type = "bezier", points = { { 0.25, 1 },  { 0.5, 1 } } })
  hl.curve("linear",     { type = "bezier", points = { { 0, 0 },     { 1, 1 } } })
  hl.curve("novaSpring", { type = "spring", mass = 1, stiffness = 190, damping = 28 })

  hl.animation({ leaf = "global",           enabled = true, speed = 8, bezier = "default" })
  hl.animation({ leaf = "windows",          enabled = true, speed = 5, spring = "novaSpring" })
  hl.animation({ leaf = "windowsIn",        enabled = true, speed = 4, spring = "novaSpring", style = "popin 94%" })
  hl.animation({ leaf = "windowsOut",       enabled = true, speed = 2, bezier = "novaOut", style = "popin 94%" })
  hl.animation({ leaf = "windowsMove",      enabled = true, speed = 4, spring = "novaSpring" })
  hl.animation({ leaf = "border",           enabled = true, speed = 6, bezier = "smooth" })
  hl.animation({ leaf = "fade",             enabled = true, speed = 4, bezier = "smooth" })
  hl.animation({ leaf = "layers",           enabled = true, speed = 4, bezier = "nova" })
  hl.animation({ leaf = "layersIn",         enabled = true, speed = 4, bezier = "nova", style = "popin 96%" })
  hl.animation({ leaf = "layersOut",        enabled = true, speed = 2, bezier = "novaOut", style = "fade" })
  hl.animation({ leaf = "workspaces",       enabled = true, speed = 4, bezier = "nova", style = "slidefade 8%" })
  hl.animation({ leaf = "specialWorkspace", enabled = true, speed = 4, bezier = "nova", style = "slidefadevert 20%" })

  local level = current_level(look)
  apply_level(look, level)

  -- Rafraîchissement : appelé par nova-mode (hyprctl eval "nova_refresh()")
  -- et toutes les 10 s pour suivre le branchement / débranchement du secteur.
  local last = level
  _G.nova_refresh = function()
    local now = current_level(look)
    if now ~= last then
      last = now
      apply_level(look, now)
    end
    return now
  end

  -- Le minuteur n'est créé que dans une vraie session : `Hyprland --verify-config`
  -- déclenche aussi « config.reloaded » mais n'a pas de boucle d'événements
  -- (et n'a pas de HYPRLAND_INSTANCE_SIGNATURE).
  local function start_power_watch()
    if _G.nova_power_timer then return end
    _G.nova_power_timer = hl.timer(function() _G.nova_refresh() end, { timeout = 10000, type = "repeat" })
  end
  hl.on("hyprland.start", function()
    _G.nova_session_started = true
    start_power_watch()
  end)
  hl.on("config.reloaded", function()
    if _G.nova_session_started or os.getenv("HYPRLAND_INSTANCE_SIGNATURE") then
      start_power_watch()
    end
  end)
  hl.on("config.unload", function() _G.nova_power_timer = nil end)
end

return M
