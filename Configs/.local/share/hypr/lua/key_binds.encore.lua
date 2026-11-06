-- Fragment for upstream Configs/.local/share/hypr/lua/key_binds.lua.
-- MOD + ALT + {L,K,M} are unbound upstream as of 2026-11-04.
_F = {description = "[Utilities] toggle encore lyrics on the desktop"}
hl.bind(MOD .. " + ALT + L", hl.dsp.exec_cmd("hyde-shell encore toggle"), _F)
_F = {description = "[Utilities] cycle encore lyrics style"}
hl.bind(MOD .. " + ALT + K", hl.dsp.exec_cmd("hyde-shell encore style next"), _F)
_F = {description = "[Utilities] open Encore"}
hl.bind(MOD .. " + ALT + M", hl.dsp.exec_cmd("hyde-shell encore app"), _F)
