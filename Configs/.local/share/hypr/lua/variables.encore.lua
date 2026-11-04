-- Fragment for upstream Configs/.local/share/hypr/lua/variables.lua.
-- Add next to the other hc.start entries. start_up.lua runs only the keys it
-- names, so start_up.encore.lua must be merged too. The service exits at once
-- unless [encore] enable = true in ~/.config/hyde/config.toml.
hc.start.encore = "hyde-shell app -u " .. unt .. "-encore.service -t " .. svc .. " -- encore.sh daemon --if-enabled"
