-- Nova OS — variables d'environnement de la session Wayland.
local util = require("nova.util")
local M = {}

function M.apply(_cfg)
  local cursor = util.first_existing({
    { check = "/usr/share/icons/Bibata-Modern-Ice/index.theme", value = "Bibata-Modern-Ice" },
    { check = "/usr/share/icons/capitaine-cursors/index.theme", value = "capitaine-cursors" },
  }, "Adwaita")

  hl.env("XCURSOR_THEME", cursor)
  hl.env("XCURSOR_SIZE", "24")
  hl.env("HYPRCURSOR_SIZE", "24")
  -- Les configurations Nova par défaut (Waybar, swaync, fuzzel, GTK...) vivent
  -- dans /usr/share/nova/xdg ; celles de ~/.config restent prioritaires.
  hl.env("XDG_CONFIG_DIRS", "/usr/share/nova/xdg:/etc/xdg")
  hl.env("XDG_CURRENT_DESKTOP", "Hyprland")
  hl.env("XDG_SESSION_TYPE", "wayland")
  hl.env("XDG_SESSION_DESKTOP", "Hyprland")
  hl.env("QT_QPA_PLATFORM", "wayland;xcb")
  hl.env("QT_QPA_PLATFORMTHEME", "gtk3")
  hl.env("QT_WAYLAND_DISABLE_WINDOWDECORATION", "1")
  hl.env("GDK_BACKEND", "wayland,x11,*")
  hl.env("ELECTRON_OZONE_PLATFORM_HINT", "auto")
  hl.env("MOZ_ENABLE_WAYLAND", "1")
  hl.env("NOVA_SESSION", "1")
end

return M
