#!/usr/bin/env bash
# hyde-shell entry point for encore (hyde-shell runs <name>.sh before <name>.py).
# encore needs PyGObject (Playerctl, GTK4 layer-shell). HyDE's python venv is
# created without system site-packages and cannot import gi, so encore runs on
# the system python3 instead. See docs/DECISIONS.md #8.
# gtk4-layer-shell must be loaded before libwayland-client, so the overlay
# subcommand preloads it.
if [ "$1" = "overlay" ] || [ "$1" = "glow" ]; then
    export LD_PRELOAD="/usr/lib/libgtk4-layer-shell.so${LD_PRELOAD:+:$LD_PRELOAD}"
fi
exec python3 "$(dirname "${BASH_SOURCE[0]}")/encore.py" "$@"
