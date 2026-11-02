-- ███╗   ██╗ ██████╗ ██╗   ██╗ █████╗
-- ████╗  ██║██╔═══██╗██║   ██║██╔══██╗
-- ██╔██╗ ██║██║   ██║██║   ██║███████║
-- ██║╚██╗██║██║   ██║╚██╗ ██╔╝██╔══██║
-- ██║ ╚████║╚██████╔╝ ╚████╔╝ ██║  ██║
-- ╚═╝  ╚═══╝ ╚═════╝   ╚═══╝  ╚═╝  ╚═╝  OS
--
-- Configuration Hyprland de Nova OS (Lua, Hyprland >= 0.57).
-- Installée dans /usr/share/nova/hypr et mise à jour avec le système.
--
-- Utilisation, dans ~/.config/hypr/hyprland.lua :
--   package.path = "/usr/share/nova/hypr/?.lua;/usr/share/nova/hypr/?/init.lua;" .. package.path
--   require("nova").setup({ apps = { terminal = "kitty" } })
local util = require("nova.util")

local M = {}

function M.setup(user)
  local cfg = util.merge(require("nova.defaults"), user or {})
  require("nova.env").apply(cfg)
  require("nova.look").apply(cfg)
  require("nova.input").apply(cfg)
  require("nova.binds").apply(cfg)
  require("nova.rules").apply(cfg)
  require("nova.autostart").apply(cfg)
  M.config = cfg
  return cfg
end

return M
