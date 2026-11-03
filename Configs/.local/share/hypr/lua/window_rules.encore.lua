-- Fragment for upstream Configs/.local/share/hypr/lua/window_rules.lua.
-- The encore settings panel floats like a menu, docked at the top right.
hl.window_rule(
  {
    name = "encore_settings",
    match = {
      class = "^org\\.hyde\\.encore\\.settings$"
    },
    float = true,
    pin = true,
    size = "360 (monitor_h*0.82)",
    move = "(monitor_w-380) 56",
    opacity = "1.0 override 1.0 override"
  }
)
