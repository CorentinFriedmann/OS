-- Nova OS — clavier, pavé tactile, gestes.
local util = require("nova.util")
local M = {}

function M.apply(cfg)
  local layout, variant, options = util.system_keyboard()
  local kb = cfg.keyboard or {}

  hl.config({
    input = {
      kb_layout = kb.layout or layout,
      kb_variant = kb.variant or variant,
      kb_options = (kb.options and kb.options ~= "") and kb.options or options,
      repeat_rate = 35,
      repeat_delay = 250,
      follow_mouse = 1,
      sensitivity = 0,
      touchpad = {
        natural_scroll = cfg.touchpad.natural_scroll,
        tap_to_click = cfg.touchpad.tap_to_click,
        disable_while_typing = true,
        clickfinger_behavior = true,
        scroll_factor = 0.8,
      },
    },
    gestures = { workspace_swipe_cancel_ratio = 0.2 },
    cursor = {
      hide_on_key_press = true,
      inactive_timeout = 5,
      -- Machines virtuelles (VirtualBox, VMware…) : le curseur matériel y est
      -- souvent invisible ou décalé, on le dessine nous-mêmes.
      no_hardware_cursors = util.virtual_machine() and "Enabled" or "Auto",
    },
    binds = { workspace_back_and_forth = true, allow_workspace_cycles = true },
  })

  -- Trois doigts : changer de bureau virtuel
  hl.gesture({ fingers = 3, direction = "horizontal", action = "workspace" })
end

return M
