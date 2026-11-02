-- Nova OS — réglages par défaut du bureau.
-- Ne modifie pas ce fichier : surcharge ce que tu veux dans
-- ~/.config/hypr/hyprland.lua via require("nova").setup({ ... }).
return {
  mod = "SUPER",

  apps = {
    terminal  = "ghostty",
    browser   = "firefox",
    files     = "nautilus --new-window",
    launcher  = "nova-launcher",
    assistant = "nova-assistant toggle",
    editor    = "code",
    calculator = "gnome-calculator",
  },

  -- nil = disposition détectée automatiquement (réglée à l'installation)
  keyboard = { layout = nil, variant = nil, options = "" },

  touchpad = { natural_scroll = true, tap_to_click = true },

  look = {
    gaps_in = 5,
    gaps_out = 10,
    border_size = 2,
    rounding = 14,
    blur = true,
    glow = true,             -- halo néon autour de la fenêtre active
    shadow = true,
    animations = true,
    border_animation = false, -- dégradé tournant : joli mais consomme sur batterie
    inactive_opacity = 0.96,
    -- Sur batterie, Nova coupe automatiquement les effets coûteux
    power_aware = true,
  },

  wallpaper = "/usr/share/backgrounds/nova/nova-city.jpg",

  -- Programmes lancés à l'ouverture de session
  autostart = {
    "nova-session-start", -- environnement + services (agent polkit, démon Nova IA), dans l'ordre
    "nova-wallpaper restore",
    "nova-bar", -- Waybar avec la configuration Nova (notifications : nova-session-start)
    "nova-osd server",
    "nova-idle",
    "wl-paste --type text --watch cliphist store",
    "wl-paste --type image --watch cliphist store",
    "nova-welcome",
  },
  -- Applets de la zone de notification (réseau, bluetooth)
  autostart_extra = {
    "nm-applet --indicator",
    "blueman-applet",
  },
}
