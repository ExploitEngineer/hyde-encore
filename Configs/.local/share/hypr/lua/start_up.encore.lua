-- Fragment for upstream Configs/.local/share/hypr/lua/start_up.lua.
-- start_up.lua runs a fixed list of hc.start keys, so hc.start.encore (see
-- variables.encore.lua) only starts once this line sits in its
-- "hyprland.start" handler, after check_exec(hs.hyde_config):
check_exec(hs.encore)
