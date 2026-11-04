-- Fragment for upstream Configs/.local/share/hypr/lua/window_rules.lua.
-- The Encore window floats, centered, at its designed size; full screen still works.
hl.window_rule(
  {
    name = "encore_app",
    match = {
      class = "^org\\.hyde\\.encore$"
    },
    float = true,
    center = true,
    size = "960 700",
    opacity = "1.0 override 1.0 override"
  }
)
