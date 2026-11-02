-- Nova OS — raccourcis clavier.
-- Pensés pour les habitués de Windows (Super+E, Super+L, Super+V, Super+.,
-- Super+Maj+S...) et compatibles AZERTY : les chiffres utilisent les codes
-- physiques des touches, donc pas besoin d'appuyer sur Maj.
-- Super+F1 affiche la liste complète à l'écran.
local M = {}

function M.apply(cfg)
  local mod = cfg.mod
  local apps = cfg.apps
  local exec = hl.dsp.exec_cmd

  local function bind(keys, dispatcher, description, opts)
    opts = opts or {}
    opts.description = description
    hl.bind(keys, dispatcher, opts)
  end

  -- Applications ----------------------------------------------------------
  bind(mod .. " + Return", exec(apps.terminal), "Terminal")
  bind(mod .. " + space", exec(apps.assistant), "Assistant IA Nova")
  bind(mod .. " + D", exec(apps.launcher), "Lanceur d'applications")
  bind(mod .. " + E", exec(apps.files), "Fichiers")
  bind(mod .. " + B", exec(apps.browser), "Navigateur web")
  bind(mod .. " + C", exec(apps.editor), "Éditeur de code")
  bind(mod .. " + V", exec("nova-clipboard"), "Historique du presse-papiers")
  bind(mod .. " + period", exec("nova-emoji"), "Emojis")
  bind(mod .. " + N", exec("swaync-client -t -sw"), "Centre de notifications")
  bind(mod .. " + F1", exec("nova-keybinds"), "Aide des raccourcis")
  bind(mod .. " + SHIFT + C", exec("hyprpicker -a -f hex"), "Pipette à couleurs")
  bind("XF86Calculator", exec(apps.calculator), "Calculatrice")
  bind("XF86Search", exec(apps.launcher), "Recherche")

  -- Système -----------------------------------------------------------------
  bind(mod .. " + L", exec("nova-lock"), "Verrouiller la session")
  bind(mod .. " + Escape", exec("nova-powermenu"), "Menu d'alimentation")
  bind("CTRL + ALT + Delete", exec("nova-powermenu"), "Menu d'alimentation")
  bind("XF86PowerOff", exec("nova-powermenu"), "Menu d'alimentation")
  bind(mod .. " + M", exec("nova-mode menu"), "Modes de performance")
  bind(mod .. " + G", exec("nova-mode toggle-game"), "Mode jeu (activer / désactiver)")

  -- Captures d'écran (comme l'outil Capture de Windows) ---------------------
  bind("Print", exec("nova-screenshot zone"), "Capture d'une zone")
  bind(mod .. " + SHIFT + S", exec("nova-screenshot zone"), "Capture d'une zone")
  bind("SHIFT + Print", exec("nova-screenshot ecran"), "Capture de tout l'écran")
  bind(mod .. " + Print", exec("nova-screenshot fenetre"), "Capture de la fenêtre active")

  -- Fenêtres ----------------------------------------------------------------
  bind(mod .. " + Q", hl.dsp.window.close(), "Fermer la fenêtre")
  bind("ALT + F4", hl.dsp.window.close(), "Fermer la fenêtre")
  bind(mod .. " + F", hl.dsp.window.fullscreen({ mode = "fullscreen", action = "toggle" }), "Plein écran")
  bind(mod .. " + SHIFT + F", hl.dsp.window.fullscreen({ mode = "maximized", action = "toggle" }), "Agrandir")
  bind(mod .. " + T", hl.dsp.window.float({ action = "toggle" }), "Fenêtre flottante / en mosaïque")
  bind(mod .. " + P", hl.dsp.window.pin(), "Épingler sur tous les bureaux")
  bind(mod .. " + J", hl.dsp.layout("togglesplit"), "Basculer la découpe horizontale / verticale")
  bind("ALT + Tab", hl.dsp.window.cycle_next(), "Fenêtre suivante")
  bind("ALT + SHIFT + Tab", hl.dsp.window.cycle_next({ prev = true }), "Fenêtre précédente")

  local directions = { left = "la gauche", right = "la droite", up = "le haut", down = "le bas" }
  for key, label in pairs(directions) do
    bind(mod .. " + " .. key, hl.dsp.focus({ direction = key }), "Focus vers " .. label)
    bind(mod .. " + SHIFT + " .. key, hl.dsp.window.move({ direction = key }), "Déplacer la fenêtre vers " .. label)
  end
  local resize = { left = { -40, 0 }, right = { 40, 0 }, up = { 0, -40 }, down = { 0, 40 } }
  for key, delta in pairs(resize) do
    bind(mod .. " + CTRL + " .. key, hl.dsp.window.resize({ x = delta[1], y = delta[2], relative = true }),
      "Redimensionner", { repeating = true })
  end

  -- Souris : Super + clic gauche = déplacer, Super + clic droit = redimensionner
  hl.bind(mod .. " + mouse:272", hl.dsp.window.drag(), { mouse = true, description = "Déplacer à la souris" })
  hl.bind(mod .. " + mouse:273", hl.dsp.window.resize(), { mouse = true, description = "Redimensionner à la souris" })

  -- Bureaux virtuels (codes physiques 10..19 = rangée des chiffres) ----------
  for i = 1, 10 do
    local code = "code:" .. tostring(9 + i)
    bind(mod .. " + " .. code, hl.dsp.focus({ workspace = i }), "Aller au bureau " .. i)
    bind(mod .. " + SHIFT + " .. code, hl.dsp.window.move({ workspace = i }), "Envoyer la fenêtre au bureau " .. i)
  end
  bind(mod .. " + Tab", hl.dsp.focus({ workspace = "e+1" }), "Bureau suivant")
  bind(mod .. " + SHIFT + Tab", hl.dsp.focus({ workspace = "e-1" }), "Bureau précédent")
  bind(mod .. " + mouse_down", hl.dsp.focus({ workspace = "e+1" }), "Bureau suivant")
  bind(mod .. " + mouse_up", hl.dsp.focus({ workspace = "e-1" }), "Bureau précédent")

  -- Bloc-notes caché (bureau spécial)
  bind(mod .. " + S", hl.dsp.workspace.toggle_special("nova"), "Afficher / masquer le bureau caché")
  bind(mod .. " + ALT + S", hl.dsp.window.move({ workspace = "special:nova" }), "Envoyer au bureau caché")

  -- Touches multimédia (avec affichage néon à l'écran) ----------------------
  local media = { locked = true, repeating = true }
  bind("XF86AudioRaiseVolume", exec("nova-osd volume-up"), "Volume +", media)
  bind("XF86AudioLowerVolume", exec("nova-osd volume-down"), "Volume -", media)
  bind("XF86AudioMute", exec("nova-osd mute"), "Couper le son", { locked = true })
  bind("XF86AudioMicMute", exec("nova-osd mic-mute"), "Couper le micro", { locked = true })
  bind("XF86MonBrightnessUp", exec("nova-osd brightness-up"), "Luminosité +", media)
  bind("XF86MonBrightnessDown", exec("nova-osd brightness-down"), "Luminosité -", media)
  bind("XF86AudioPlay", exec("playerctl play-pause"), "Lecture / pause", { locked = true })
  bind("XF86AudioPause", exec("playerctl play-pause"), "Lecture / pause", { locked = true })
  bind("XF86AudioNext", exec("playerctl next"), "Piste suivante", { locked = true })
  bind("XF86AudioPrev", exec("playerctl previous"), "Piste précédente", { locked = true })
end

return M
