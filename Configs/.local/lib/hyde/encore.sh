#!/usr/bin/env bash
# hyde-shell entry point for encore (hyde-shell runs <name>.sh before <name>.py).
# encore needs PyGObject (Playerctl, GTK4 layer-shell). HyDE's python venv is
# created without system site-packages and cannot import gi, so encore runs on
# the system python3 instead. See docs/DECISIONS.md #8.
exec python3 "$(dirname "${BASH_SOURCE[0]}")/encore.py" "$@"
