-- Nova OS — règles des fenêtres et des calques (barres, menus, overlays).
local M = {}

local function floating(name, match, extra)
  local spec = { name = name, match = match, float = true, center = true }
  for k, v in pairs(extra or {}) do spec[k] = v end
  hl.window_rule(spec)
end

function M.apply(_cfg)
  -- Ignorer les demandes « agrandir » des applications (on garde la mosaïque)
  hl.window_rule({ name = "nova-no-maximize", match = { class = ".*" }, suppress_event = "maximize" })
  -- Correctif glisser-déposer XWayland
  hl.window_rule({
    name = "nova-xwayland-drag",
    match = { class = "^$", title = "^$", xwayland = true, float = true, fullscreen = false, pin = false },
    no_focus = true,
  })

  -- Petits utilitaires en fenêtres flottantes
  floating("nova-float-audio", { class = "^(org.pulseaudio.pavucontrol|pavucontrol)$" }, { size = "900 600" })
  floating("nova-float-bluetooth", { class = "^(blueman-manager|.blueman-manager-wrapped)$" }, { size = "760 520" })
  floating("nova-float-network", { class = "^(nm-connection-editor)$" }, { size = "760 520" })
  floating("nova-float-calc", { class = "^(org.gnome.Calculator)$" })
  floating("nova-float-portal", { class = "^(xdg-desktop-portal-gtk)$" }, { size = "1000 700" })
  floating("nova-float-polkit", { class = "^(hyprpolkitagent|org.hyprland.hyprpolkitagent)$" })
  floating("nova-float-dialogs", { title = "^(Ouvrir.*|Enregistrer.*|Open File.*|Save As.*|Sélectionner.*)$" }, { size = "1000 700" })
  floating("nova-float-installer", { class = "^(nova-installer)$" }, { size = "1100 720" })

  -- Vidéo « image dans l'image » : épinglée dans le coin
  hl.window_rule({
    name = "nova-pip",
    match = { title = "^(Picture-in-Picture|Incrustation vidéo)$" },
    float = true,
    pin = true,
    size = "640 360",
    move = "monitor_w-660 monitor_h-380",
    no_glow = true,
  })

  -- Steam et jeux : pas de veille en plein écran, latence minimale
  hl.window_rule({ name = "nova-idle-fullscreen", match = { class = ".*" }, idle_inhibit = "fullscreen" })
  hl.window_rule({ name = "nova-games-tearing", match = { class = "^(steam_app_.*|gamescope)$" }, immediate = true })
  floating("nova-steam-friends", { class = "^(steam)$", title = "^(Liste d'amis|Friends List)$" }, { size = "420 720" })

  -- Calques (layer-shell) : verre dépoli sous la barre, les menus et l'assistant
  local blurred = {
    { "waybar", 0.25 },
    { "launcher", 0.2 },             -- fuzzel
    { "swaync-control-center", 0.2 },
    { "swaync-notification-window", 0.2 },
    { "swayosd", 0.2 },
    { "nova-assistant", 0.15 },
  }
  for _, item in ipairs(blurred) do
    hl.layer_rule({
      name = "nova-blur-" .. item[1],
      match = { namespace = "^" .. item[1] .. "$" },
      blur = true,
      ignore_alpha = item[2],
    })
  end
  hl.layer_rule({ name = "nova-anim-launcher", match = { namespace = "^launcher$" }, animation = "popin 90%" })
  hl.layer_rule({ name = "nova-anim-assistant", match = { namespace = "^nova-assistant$" }, animation = "popin 94%" })
  hl.layer_rule({ name = "nova-anim-swaync", match = { namespace = "^swaync-control-center$" }, animation = "slide right" })

  -- Bureau caché : marges plus larges pour un effet « carte flottante »
  hl.workspace_rule({ workspace = "special:nova", gaps_out = 60 })
end

return M
