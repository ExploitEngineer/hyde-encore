-- Fragment for upstream Configs/.local/share/hypr/lua/window_rules.lua.
-- The encore player is a floating, centered app window.
hl.window_rule(
  {
    name = "encore_player",
    match = {
      class = "^org\\.hyde\\.encore\\.player$"
    },
    float = true,
    center = true,
    size = "960 660",
    opacity = "1.0 override 1.0 override"
  }
)
