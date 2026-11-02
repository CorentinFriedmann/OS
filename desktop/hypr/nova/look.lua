-- Nova OS — apparence : néon cyberpunk, halo, flou, animations.
--
-- Effets « intelligents » : sur batterie (ou en mode éco / jeu), les effets
-- coûteux sont réduits automatiquement pour économiser l'énergie et les FPS.
-- Le mode est piloté par nova-mode via le fichier $XDG_RUNTIME_DIR/nova/visual-mode
-- (valeurs : auto | full | eco | game).
local util = require("nova.util")
local M = {}

local NEON = {
  border = { colors = { "rgba(00f0ffff)", "rgba(8a5cffff)", "rgba(ff2bd6ff)" }, angle = 45 },
  border_inactive = "rgba(8a5cff30)",
  glow = { colors = { "rgba(00f0ff66)", "rgba(ff2bd666)" }, angle = 45 },
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
      col = { active_border = NEON.border, inactive_border = NEON.border_inactive },
    },
    decoration = {
      shadow = {
        enabled = look.shadow and fancy,
        range = 22,
        render_power = 3,
        color = "rgba(00000099)",
        color_inactive = "rgba(00000055)",
      },
      glow = {
        enabled = look.glow and not playing,
        range = fancy and 14 or 8,
        render_power = 3,
        color = NEON.glow,
        color_inactive = "rgba(00000000)",
      },
      blur = {
        enabled = look.blur and not playing,
        size = fancy and 8 or 4,
        passes = fancy and 3 or 1,
        noise = 0.015,
        contrast = 0.95,
        brightness = 0.85,
        vibrancy = 0.22,
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

  hl.monitor({ output = "", mode = "preferred", position = "auto", scale = "auto" })

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
      background_color = "rgb(05060d)",
      focus_on_activate = true,
      mouse_move_enables_dpms = true,
      key_press_enables_dpms = true,
      vrr = 2,
      font_family = "Inter",
    },
    ecosystem = { no_update_news = true, no_donation_nag = true },
  })

  -- Courbes : réactives avec un léger rebond, signature de Nova
  hl.curve("nova",       { type = "bezier", points = { { 0.05, 0.9 }, { 0.1, 1.05 } } })
  hl.curve("novaOut",    { type = "bezier", points = { { 0.3, 0 },    { 0.8, 0.15 } } })
  hl.curve("smooth",     { type = "bezier", points = { { 0.25, 1 },   { 0.5, 1 } } })
  hl.curve("linear",     { type = "bezier", points = { { 0, 0 },      { 1, 1 } } })
  hl.curve("novaSpring", { type = "spring", mass = 1, stiffness = 220, damping = 22 })

  hl.animation({ leaf = "global",           enabled = true, speed = 8, bezier = "default" })
  hl.animation({ leaf = "windows",          enabled = true, speed = 5, spring = "novaSpring" })
  hl.animation({ leaf = "windowsIn",        enabled = true, speed = 4, spring = "novaSpring", style = "popin 80%" })
  hl.animation({ leaf = "windowsOut",       enabled = true, speed = 2, bezier = "novaOut", style = "popin 80%" })
  hl.animation({ leaf = "windowsMove",      enabled = true, speed = 4, spring = "novaSpring" })
  hl.animation({ leaf = "border",           enabled = true, speed = 6, bezier = "smooth" })
  hl.animation({ leaf = "fade",             enabled = true, speed = 4, bezier = "smooth" })
  hl.animation({ leaf = "layers",           enabled = true, speed = 4, bezier = "nova" })
  hl.animation({ leaf = "layersIn",         enabled = true, speed = 4, bezier = "nova", style = "popin 92%" })
  hl.animation({ leaf = "layersOut",        enabled = true, speed = 2, bezier = "novaOut", style = "fade" })
  hl.animation({ leaf = "workspaces",       enabled = true, speed = 4, bezier = "smooth", style = "slidefade 15%" })
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
