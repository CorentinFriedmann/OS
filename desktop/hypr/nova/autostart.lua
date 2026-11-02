-- Nova OS — programmes lancés à l'ouverture de la session.
local M = {}

local function shell_quote(s)
  return "'" .. tostring(s):gsub("'", "'\\''") .. "'"
end

function M.apply(cfg)
  hl.on("hyprland.start", function()
    for _, cmd in ipairs(cfg.autostart or {}) do
      -- Le fond d'écran choisi dans setup() sert de valeur par défaut
      if cmd == "nova-wallpaper restore" and cfg.wallpaper then
        cmd = cmd .. " " .. shell_quote(cfg.wallpaper)
      end
      hl.exec_cmd(cmd)
    end
    for _, cmd in ipairs(cfg.autostart_extra or {}) do hl.exec_cmd(cmd) end
  end)
end

return M
