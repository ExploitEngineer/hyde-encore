-- Fragment for upstream Configs/.local/share/hypr/lua/key_binds.lua.
-- MOD + ALT + L is unbound upstream as of 2026-11-04.
_F = {description = "[Utilities] toggle encore lyrics overlay"}
hl.bind(MOD .. " + ALT + L", hl.dsp.exec_cmd("hyde-shell encore toggle"), _F)
