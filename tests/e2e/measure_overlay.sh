#!/usr/bin/env bash
# Measures overlay CPU in three phases: animating, paused, hidden (intro gap).
# Usage: bash tests/e2e/measure_overlay.sh [seconds-per-phase]
set -u
PHASE_S="${1:-10}"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
RUN="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/hyde"
cd "$REPO"

# Follow only the fake player, so a real Spotify or browser session on the
# desktop cannot steal the daemon mid-measurement.
export ENCORE_PLAYERS="encoretest"
python3 tests/e2e/fake_mpris.py & FAKE=$!
sleep 1
python3 "$HOME/.local/lib/hyde/encore.py" daemon >/dev/null 2>&1 & DAEMON=$!
sleep 1
bash "$HOME/.local/lib/hyde/encore.sh" overlay >/dev/null 2>&1 &
sleep 3
OV="$(cat "$RUN/encore-overlay.pid" 2>/dev/null)"
if [ -z "$OV" ] || ! kill -0 "$OV" 2>/dev/null; then
    echo "overlay did not start"; kill "$FAKE" "$DAEMON" 2>/dev/null; exit 1
fi
cpu() { awk '{print $14+$15}' "/proc/$1/stat"; }
phase() { # name, pid
    local a b
    a=$(cpu "$2"); sleep "$PHASE_S"; b=$(cpu "$2")
    echo "$1: $((b - a)) ticks over ${PHASE_S}s ($(awk -v t=$((b-a)) -v s="$PHASE_S" 'BEGIN{printf "%.1f", t/s}')% of one core)"
}
playerctl -p encoretest position 25; playerctl -p encoretest play; sleep 2
phase "overlay animating" "$OV"
phase "daemon  animating" "$DAEMON"
playerctl -p encoretest pause; sleep 2
phase "overlay paused   " "$OV"
playerctl -p encoretest position 2; playerctl -p encoretest play; sleep 1
phase "overlay hidden   " "$OV"
kill -TERM "$OV" 2>/dev/null; kill -INT "$DAEMON" 2>/dev/null; kill "$FAKE" 2>/dev/null
sleep 1
ls "$RUN" | grep encore || echo "runtime clean"
