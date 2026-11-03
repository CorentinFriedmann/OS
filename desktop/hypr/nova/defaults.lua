-- Nova OS — réglages par défaut du bureau.
-- Ne modifie pas ce fichier : surcharge ce que tu veux dans
-- ~/.config/hypr/hyprland.lua via require("nova").setup({ ... }).
return {
  mod = "SUPER",

  apps = {
    terminal  = "nova-terminal", -- Ghostty, ou foot sans carte graphique 3D
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
    gaps_in = 6,
    gaps_out = 12,
    border_size = 1,
    rounding = 16,
    blur = true,
    glow = false,            -- halo lumineux autour de la fenêtre active (désactivé : style épuré)
    shadow = true,
    animations = true,
    border_animation = false, -- dégradé tournant : joli mais consomme sur batterie
    inactive_opacity = 0.97,
    -- Sur batterie, Nova coupe automatiquement les effets coûteux
    power_aware = true,
  },

  wallpaper = "/usr/share/backgrounds/nova/nova-verre.jpg",

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
