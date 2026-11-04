#!/usr/bin/env python3
"""Measure encore's CPU cost on the isolated harness.

Runs the repo's daemon (and optionally the overlay or glow) against a
fake player on a private bus and runtime dir, then reports the share of
one core each process used while playing, paused, and playing with no
lyric line (outro). The owner's session is never touched; --overlay and
--glow do draw on the real screen, so run them only when that is fine.

Usage: python3 tests/e2e/measure.py [--seconds N] [--overlay] [--glow]
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import LIB, Harness, write_png

ARTIST, TITLE = "Rick Astley", "Never Gonna Give You Up"  # fake_mpris track 1
# invented lines every 2 s for three minutes, so the cursor keeps moving
LRC = "".join(
    f"[{t // 60:02d}:{t % 60:02d}.00]measured line number {t}\n" for t in range(1, 180, 2)
)
CLK_TCK = os.sysconf("SC_CLK_TCK")


def cpu_ticks(pid: int) -> int:
    fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    return int(fields[11]) + int(fields[12])  # utime + stime


def phase(name: str, pids: dict[str, int], seconds: float) -> None:
    before = {who: cpu_ticks(pid) for who, pid in pids.items()}
    time.sleep(seconds)
    for who, pid in pids.items():
        used = cpu_ticks(pid) - before[who]
        share = used / (seconds * CLK_TCK) * 100
        print(f"{name:14} {who:8} {used:4d} ticks over {seconds:.0f}s = {share:5.2f}% of one core")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seconds", type=float, default=10.0, help="length of each phase")
    parser.add_argument("--overlay", action="store_true", help="also measure the lyrics overlay")
    parser.add_argument("--glow", action="store_true", help="also measure the edge glow")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp, Harness(Path(tmp)) as h:
        h.write_lrc(ARTIST, TITLE, LRC)
        h.start_player(art=str(write_png(Path(tmp) / "cover.png")))
        pids = {"daemon": h.start_daemon().pid}
        h.ctl("encoretest", "play")
        h.wait(lambda s: s["status"] == "playing" and s["lyrics"] and s["track"]["art"], 15)
        if args.overlay:
            pids["overlay"] = h._spawn(["bash", str(LIB / "encore.sh"), "overlay"], "ov.log").pid
        if args.glow:
            pids["glow"] = h._spawn(["bash", str(LIB / "encore.sh"), "glow", "--run"], "gl.log").pid
        time.sleep(2.0)  # let every process settle before counting

        phase("playing", pids, args.seconds)
        h.ctl("encoretest", "pause")
        h.wait(lambda s: s["status"] == "paused")
        phase("paused", pids, args.seconds)
        h.ctl("encoretest", "position", "200")
        h.ctl("encoretest", "play")
        h.wait(lambda s: s["status"] == "playing" and s["line"] is None)
        phase("no lyric line", pids, args.seconds)
        print(f"private runtime dir: {h.run}")
    print("harness torn down; the owner's runtime dir was never used")
    return 0


if __name__ == "__main__":
    sys.exit(main())
