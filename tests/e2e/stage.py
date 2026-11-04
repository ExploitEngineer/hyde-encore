#!/usr/bin/env python3
"""Render encore's real surfaces on a hidden monitor and capture them.

Adds a virtual monitor `encore-lab` to the running Hyprland (parked at
20000,20000 so the mouse cannot reach it, removed afterwards), runs the
private harness (fake player, private bus and runtime dir, repo daemon),
starts the overlay and optionally the glow on that monitor, seeks the fake
player to each requested position and saves `grim -o encore-lab` stills,
plus an optional clip. Nothing shows on the owner's screen.

Usage:
  python3 tests/e2e/stage.py --style stack --at 2.9,5.0,12.4 [--glow] [--clip 6]
      [--look size=40 --look motion=false] [--ref .reference/site/hero-1.png]
  python3 tests/e2e/stage.py --no-overlay --app home [--relaunch] --cover cover.jpg --at 5.0
Output goes to .stage/<style>/ (gitignored).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Self

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import LIB, REPO, Harness, write_png

from encorelib.look import update_look

# a fresh name per run: Hyprland moves a workspace back to the monitor it was
# last on, so a reused name pulls one of the owner's workspaces onto the lab
LAB = f"encore-lab-{os.getpid()}"
LAB_CLASS = "org.hyde.encore.lab"  # the stage copy of the Encore window
ARTIST, TITLE = "Rick Astley", "Never Gonna Give You Up"  # fake_mpris track 1
# original lyrics, word-timed; glyph triggers and one CJK line on purpose
LRC = """[00:02.00]<00:02.00>Neon <00:02.45>on <00:02.65>the <00:02.80>city <00:03.30>floor<00:03.90>
[00:04.20]<00:04.20>I <00:04.35>call <00:04.70>your <00:04.95>name <00:05.40>at <00:05.60>night<00:06.30>
[00:06.60]<00:06.60>Every <00:07.00>light <00:07.40>is <00:07.55>moving <00:08.10>left<00:08.70>
[00:09.00]<00:09.00>Hold <00:09.35>the <00:09.50>time <00:09.95>a <00:10.05>little <00:10.50>longer<00:11.30>
[00:11.60]<00:11.60>夜<00:11.90>に<00:12.15>駆<00:12.40>け<00:12.60>る<00:12.90>
[00:13.20]<00:13.20>Drive <00:13.60>until <00:14.00>the <00:14.15>stars <00:14.60>fall <00:15.00>down<00:15.80>
[00:16.20]<00:16.20>And <00:16.40>we <00:16.55>never <00:16.95>say <00:17.25>goodbye<00:18.10>
"""


def hyprctl(*args: str) -> str:
    return subprocess.run(
        ["hyprctl", *args], capture_output=True, text=True, check=False, timeout=10
    ).stdout.strip()


class Lab:
    """A hidden virtual monitor in the running Hyprland session."""

    def __enter__(self) -> Self:
        if LAB in self.names():
            hyprctl("output", "remove", LAB)
        owners = {w["id"] for w in json.loads(hyprctl("workspaces", "-j") or "[]")}
        hyprctl("output", "create", "headless", LAB)
        deadline = time.monotonic() + 5
        while LAB not in self.names():
            if time.monotonic() > deadline:
                raise RuntimeError("Hyprland did not create the lab monitor")
            time.sleep(0.05)
        hyprctl(
            "eval",
            f'hl.monitor({{output = "{LAB}", mode = "1920x1080@60", '
            f'position = "20000x20000", scale = 1}})',
        )
        workspace = self.monitor()["activeWorkspace"]
        if workspace["id"] in owners:  # never show or move the owner's windows
            hyprctl("output", "remove", LAB)
            raise RuntimeError(f"the lab monitor took workspace {workspace['name']!r}; removed it")
        return self

    def __exit__(self, *_exc) -> None:
        hyprctl("output", "remove", LAB)

    @staticmethod
    def names() -> list[str]:
        try:
            return [m["name"] for m in json.loads(hyprctl("monitors", "all", "-j") or "[]")]
        except ValueError:
            return []

    @staticmethod
    def monitor() -> dict:
        for m in json.loads(hyprctl("monitors", "all", "-j") or "[]"):
            if m["name"] == LAB:
                return m
        raise RuntimeError("lab monitor vanished")

    @staticmethod
    def capture(path: Path) -> Path:
        subprocess.run(["grim", "-o", LAB, str(path)], check=True, timeout=10)
        return path


def default_cover(tmp: Path) -> Path:
    covers = sorted(
        (Path.home() / ".cache" / "hyde" / "encore" / "covers").glob("*.png"),
        key=lambda p: p.stat().st_mtime,
    )
    if covers:
        return Path(shutil.copy(covers[-1], tmp / "cover.png"))
    return write_png(tmp / "cover.png", 512, (190, 60, 120))


def _lab_client() -> dict | None:
    for client in json.loads(hyprctl("clients", "-j") or "[]"):
        if client.get("class") == LAB_CLASS:
            return client
    return None


def _lab_clients() -> list[dict]:
    return [c for c in json.loads(hyprctl("clients", "-j") or "[]") if c.get("class") == LAB_CLASS]


def launch_app(h: Harness, page: str, log: str = "app.log") -> subprocess.Popen:
    h.env["ENCORE_APP_ID"] = LAB_CLASS
    return h._spawn([sys.executable, str(LIB / "encore.py"), "app", "--open", page], log)


def open_app(h: Harness, lab: Lab, page: str) -> tuple[tuple[int, int, int, int], subprocess.Popen]:
    """Open the Encore window on the lab monitor; abort at once if it maps anywhere else."""
    monitor = lab.monitor()
    print(
        "rule:",
        hyprctl(
            "eval",
            'hl.window_rule({name = "encore_lab_player", '
            'match = {class = "^org\\\\.hyde\\\\.encore\\\\.lab$"}, '
            f'workspace = "{monitor["activeWorkspace"]["id"]} silent", '
            'float = true, center = true, size = "960 700", '
            'opacity = "1.0 override 1.0 override"})',
        ),
    )
    process = launch_app(h, page)
    deadline = time.monotonic() + 8
    while (client := _lab_client()) is None:
        if time.monotonic() > deadline or process.poll() is not None:
            raise RuntimeError("the stage Encore window never appeared")
        time.sleep(0.05)
    if client["monitor"] != monitor["id"]:
        process.kill()
        raise RuntimeError("the stage Encore window mapped on the owner's screen; killed it")
    time.sleep(1.5)  # art, fonts and the first poll
    client = _lab_client() or client
    (ax, ay), (aw, ah) = client["at"], client["size"]
    return (ax - monitor["x"], ay - monitor["y"], aw, ah), process


def look_value(raw: str):
    if raw.lower() in ("true", "false"):
        return raw.lower() == "true"
    try:
        return int(raw)
    except ValueError:
        return raw


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--style", default="line", help="line, stack, constellation, visual")
    parser.add_argument("--at", default="2.9,5.0,7.7,12.4,14.4", help="seconds to capture")
    parser.add_argument("--look", action="append", default=[], help="look key=value")
    parser.add_argument("--glow", action="store_true", help="also run the edge glow")
    parser.add_argument("--no-overlay", action="store_true", help="skip the lyrics overlay")
    parser.add_argument("--clip", type=float, default=0.0, help="record N seconds from 2.0")
    parser.add_argument("--app", default="", help="open the Encore window on a page: home, lyrics")
    parser.add_argument(
        "--relaunch", action="store_true", help="launch Encore a second time: one window must stay"
    )
    parser.add_argument("--cover", default="", help="cover image (default: newest cached)")
    parser.add_argument("--no-player", action="store_true", help="no music player: the idle screen")
    parser.add_argument("--no-lyrics", action="store_true", help="no lyrics for the song")
    parser.add_argument("--title", default="", help="the fake song's title")
    parser.add_argument("--artist", default="", help="the fake song's artist")
    parser.add_argument("--ref", default="", help="reference frame for a side-by-side sheet")
    parser.add_argument("--out", default="", help="output dir (default .stage/<style>)")
    args = parser.parse_args()

    out = Path(args.out or REPO / ".stage" / args.style)
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp, Lab() as lab, Harness(Path(tmp)) as h:
        # GTK_A11Y=none: the private bus cannot activate the accessibility registry,
        # which makes GtkApplication registration fail and the surface exit
        h.env.update(ENCORE_OVERLAY_MONITOR=LAB, ENCORE_GLOW_MONITOR=LAB, GTK_A11Y="none")
        if not args.no_lyrics:
            h.write_lrc(args.artist or ARTIST, args.title or TITLE, LRC)
        cover = Path(args.cover) if args.cover else default_cover(Path(tmp))
        if args.no_player:
            h.start_daemon()
            h.wait_until(lambda: h.state() is not None, "the daemon", 15)
        else:
            extra = [f"--title={args.title}"] if args.title else []
            extra += [f"--artist={args.artist}"] if args.artist else []
            h.start_player("encoretest", str(cover), *extra)
            h.start_daemon()
            h.ctl("encoretest", "play")
            h.wait(
                lambda s: (
                    s["status"] == "playing"
                    and (args.no_lyrics or s["lyrics"])
                    and s.get("lookup") == "done"
                    and s["track"]["art"]
                ),
                15,
            )
            h.ctl("encoretest", "pause")
        look = {"style": args.style}
        for item in args.look:
            key, _, value = item.partition("=")
            look[key.replace("-", "_")] = look_value(value)
        update_look(h.run / "hyde" / "encore.look", **look)
        if not args.no_overlay:
            h._spawn(["bash", str(LIB / "encore.sh"), "overlay"], "overlay.log")
        if args.glow:
            h._spawn(["bash", str(LIB / "encore.sh"), "glow", "--run"], "glow.log")
        player_box = None
        if args.app:
            player_box, _app = open_app(h, lab, args.app)
            if args.relaunch:
                second = launch_app(h, args.app, "app-second.log")
                code = second.wait(10)
                windows = len(_lab_clients())
                print(f"relaunch: second launch exited {code}, {windows} Encore window(s)")
                if code != 0 or windows != 1:
                    raise RuntimeError("a second launch must leave exactly one window")
        time.sleep(3.0)  # first frames, fonts and the art layer
        try:
            # where each encore surface really landed, and how big it is
            raw = json.loads(hyprctl("layers", "-j") or "{}")
            for monitor, data in raw.items():
                for level, items in sorted(data.get("levels", {}).items()):
                    for layer in items:
                        if "encore" in layer["namespace"]:
                            print(
                                f"layer {monitor} {layer['namespace']} level {level}: "
                                f"{layer['x']},{layer['y']} {layer['w']}x{layer['h']}"
                            )
        except ValueError:
            pass

        shots = []
        for at in [float(x) for x in args.at.split(",") if x]:
            if not args.no_player:
                h.ctl("encoretest", "position", str(at))
                h.wait(lambda s, at=at: abs(s["position"] - at) < 0.05)
            time.sleep(0.8)  # the overlay finishes its transition
            shots.append(lab.capture(out / f"{args.style}-{at:05.1f}.png"))
            print(shots[-1])
            if player_box:
                x, y, w, hh = player_box
                crop = out / f"app-{args.app}-{at:05.1f}.png"
                subprocess.run(
                    ["magick", str(shots[-1]), "-crop", f"{w}x{hh}+{x}+{y}", "+repage", str(crop)],
                    check=False,
                )
                print(crop)

        if args.clip:
            h.ctl("encoretest", "position", "2.0")
            h.ctl("encoretest", "play")
            clip = out / f"{args.style}-clip.mp4"
            rec = subprocess.Popen(
                ["wf-recorder", "-y", "-o", LAB, "-f", str(clip)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(args.clip)
            rec.send_signal(signal.SIGINT)
            rec.wait(10)
            print(clip)

        logs = out / "logs"
        shutil.rmtree(logs, ignore_errors=True)
        shutil.copytree(h.tmp / "logs", logs)
        for name in ("overlay.log", "glow.log", "app.log"):
            text = h.log(name)
            if "Traceback" in text or "CRITICAL" in text:
                print(f"--- {name}\n{text[-1500:]}", file=sys.stderr)

    if args.ref and shots:
        sheet = out / f"{args.style}-vs-ref.png"
        subprocess.run(
            ["magick", str(shots[0]), args.ref, "-resize", "x540", "+append", str(sheet)],
            check=False,
        )
        print(sheet)
    return 0


if __name__ == "__main__":
    sys.exit(main())
