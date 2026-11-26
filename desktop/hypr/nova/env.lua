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
  -- Entrées du lanceur propres à Nova (« Terminal ») et entrées techniques masquées
  local data_dirs = os.getenv("XDG_DATA_DIRS")
  if not data_dirs or data_dirs == "" then data_dirs = "/usr/local/share:/usr/share" end
  if not data_dirs:find("/usr/share/nova/data", 1, true) then
    hl.env("XDG_DATA_DIRS", "/usr/share/nova/data:" .. data_dirs)
  end
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

  -- Machine virtuelle : la carte 3D virtuelle est incomplète, et les applications GTK4
  -- (Fichiers, Calculatrice, assistant Nova…) qui s'en servent ne s'ouvrent pas ou
  -- plantent. On leur fait dessiner leurs fenêtres sans elle.
  if util.virtual_machine() then
    hl.env("GSK_RENDERER", "cairo")
    hl.env("NOVA_VM", util.virtual_machine())
  end
end

return M
