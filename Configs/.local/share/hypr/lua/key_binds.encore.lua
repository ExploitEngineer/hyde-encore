-- Fragment for upstream Configs/.local/share/hypr/lua/key_binds.lua.
-- MOD + ALT + {L,K,M,E} are unbound upstream as of 2026-11-04.
_F = {description = "[Utilities] toggle encore lyrics overlay"}
hl.bind(MOD .. " + ALT + L", hl.dsp.exec_cmd("hyde-shell encore toggle"), _F)
_F = {description = "[Utilities] cycle encore lyrics style"}
hl.bind(MOD .. " + ALT + K", hl.dsp.exec_cmd("hyde-shell encore style next"), _F)
_F = {description = "[Utilities] encore settings"}
hl.bind(MOD .. " + ALT + M", hl.dsp.exec_cmd("hyde-shell encore menu"), _F)
_F = {description = "[Utilities] encore show workspace"}
hl.bind(MOD .. " + ALT + E", hl.dsp.exec_cmd("hyde-shell encore show"), _F)
