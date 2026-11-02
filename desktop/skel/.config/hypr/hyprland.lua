-- ╔══════════════════════════════════════════════════════════════════╗
-- ║  NOVA OS — ta configuration Hyprland                             ║
-- ╚══════════════════════════════════════════════════════════════════╝
-- Le thème néon, les raccourcis et les effets de Nova sont chargés depuis
-- /usr/share/nova/hypr (mis à jour avec le système).
-- Ce fichier t'appartient : il n'est jamais écrasé par les mises à jour.
-- Les changements sont appliqués dès que tu enregistres.

package.path = "/usr/share/nova/hypr/?.lua;/usr/share/nova/hypr/?/init.lua;" .. package.path

require("nova").setup({
  -- Exemples (enlève les « -- » pour activer) :
  -- apps = { terminal = "kitty", browser = "chromium" },
  -- keyboard = { layout = "fr", variant = "bepo" },
  -- look = { gaps_out = 6, border_animation = true },
  -- wallpaper = "/home/moi/Images/fond.jpg",
})

-- Tes propres raccourcis et règles, par exemple :
-- hl.bind("SUPER + F2", hl.dsp.exec_cmd("spotify"), { description = "Spotify" })
