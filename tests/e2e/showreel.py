#!/usr/bin/env python3
"""Record Encore's demo reel on the hidden monitor: one scripted take.

The fake player plays an original song (generated cover, original word-timed
lyrics, no real artist), the window opens on Home, switches to the Stage,
then to Full screen, where the lyric style changes every few seconds. The
take is recorded with wf-recorder from the lab monitor only, then cut into
one clip at the window's aspect: the window's own rectangle while it is a
window, a centred crop of the same aspect once it fills the screen.

Usage:
  python3 tests/e2e/showreel.py [--out .stage/showreel] [--scale 1080]
Writes raw.mp4 (the whole lab monitor), cuts.json (when each shot starts)
and clip.mp4 (the edit) to the output directory. Nothing shows on the
owner's screen; no real player is touched.
"""

from __future__ import annotations

import argparse
import json
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import REPO, Harness
from stage import LAB, Lab, launch_app, open_app

from encorelib.look import update_look

TITLE, ARTIST = "Every Light", "Encore"
# a fake player on the harness's private bus, never a real one; its name is the
# chip's label on Home ("music_player" reads "Music Player")
PLAYER = "music_player"
WINDOW = (1280, 1000)  # the window during the take; Full screen is cropped to this aspect

# original lines, written for this demo; each word gets an even share of its line
LINES = [
    (1.0, "Every light is moving left"),
    (3.6, "Hold the moment, hold your breath"),
    (6.2, "City glowing on the floor"),
    (8.6, "Sing it louder than before"),
    (11.0, "Drive until the stars fall down"),
    (13.6, "Every word becomes a sound"),
    (16.2, "Call your name across the night"),
    (18.8, "Watch the colors come alive"),
    (21.4, "Run into the ocean blue"),
    (24.0, "Every song comes back to you"),
    (26.6, "Turn it up and let it play"),
    (29.2, "Every line will find its way"),
    (31.8, "Dream until the morning light"),
]
LINE_SECONDS = 2.2

# (seconds into the take, action, value): pages through the CLI, look changes
# (style and text size) through the look file, as the menus write them
SHOTS = [
    (0.0, "page", "home"),
    (2.4, "page", "stage"),
    (6.6, "page", "full"),
    (10.8, "look", {"style": "stack"}),
    (14.6, "look", {"style": "constellation", "size": 32}),
    (17.8, "look", {"style": "line", "size": 50}),
    (20.8, "look", {"style": "code", "size": 30}),
    (23.8, "look", {"style": "visual", "size": 30}),
]
TAKE_SECONDS = 27.0


def stamp(seconds: float) -> str:
    return f"{int(seconds // 60):02d}:{seconds % 60:05.2f}"


def demo_lrc() -> str:
    out = []
    for start, text in LINES:
        words = text.split()
        step = LINE_SECONDS / len(words)
        timed = "".join(f"<{stamp(start + i * step)}>{w} " for i, w in enumerate(words))
        out.append(f"[{stamp(start)}]{timed.rstrip()}<{stamp(start + LINE_SECONDS)}>")
    return "\n".join(out) + "\n"


def demo_cover(path: Path) -> Path:
    """Original abstract art: a magenta-to-violet plasma, blurred soft, with grain."""
    subprocess.run(
        [
            "magick",
            "-seed",
            "11",
            "-size",
            "1500x1500",
            "plasma:#ff2e88-#3a0ca3",
            "-blur",
            "0x24",
            "-modulate",
            "100,135",
            "(",
            "-size",
            "1500x1500",
            "radial-gradient:#ffffff20-#00000000",
            ")",
            "-compose",
            "screen",
            "-composite",
            "-attenuate",
            "0.25",
            "+noise",
            "gaussian",
            "-quality",
            "92",
            str(path),
        ],
        check=True,
    )
    return path


def cut(raw: Path, cuts: list[dict], window: dict, out: Path, width: int) -> None:
    """One clip at the window's aspect: window shots cropped to the window,
    full-screen shots to a centred rectangle of the same aspect."""
    aspect = WINDOW[0] / WINDOW[1]
    full_h = 1080
    full_w = round(full_h * aspect / 2) * 2
    height = round(width / aspect / 2) * 2
    parts = []
    for i, shot in enumerate(cuts):
        start = shot["at"]
        end = cuts[i + 1]["at"] if i + 1 < len(cuts) else TAKE_SECONDS + 0.6
        if shot["frame"] == "window":
            x, y, w, h = window["x"], window["y"], window["w"], window["h"]
        else:
            x, y, w, h = (1920 - full_w) // 2, 0, full_w, full_h
        part = out.parent / f"part-{i}.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                f"{start:.3f}",
                "-to",
                f"{end:.3f}",
                "-i",
                str(raw),
                "-vf",
                f"crop={w}:{h}:{x}:{y},scale={width}:{height}:flags=lanczos,fps=60",
                "-c:v",
                "libx264",
                "-crf",
                "14",
                "-preset",
                "slow",
                "-pix_fmt",
                "yuv420p",
                "-an",
                str(part),
            ],
            check=True,
        )
        parts.append(part)
    listing = out.parent / "parts.txt"
    listing.write_text("".join(f"file '{p.name}'\n" for p in parts))
    subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(listing),
            "-c",
            "copy",
            str(out),
        ],
        check=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(REPO / ".stage" / "showreel"))
    parser.add_argument("--scale", type=int, default=1080, help="clip width in px")
    args = parser.parse_args()
    out = Path(args.out).resolve()  # the fake player gets the cover by absolute path
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp, Lab() as lab, Harness(Path(tmp)) as h:
        h.env.update(ENCORE_OVERLAY_MONITOR=LAB, ENCORE_GLOW_MONITOR=LAB, GTK_A11Y="none")
        h.env["ENCORE_FULL_HIDE_MS"] = "900"  # the bars show briefly, then the show is clean
        h.write_lrc(ARTIST, TITLE, demo_lrc())
        cover = demo_cover(out / "cover.jpg")
        h.start_player(PLAYER, str(cover), f"--title={TITLE}", f"--artist={ARTIST}")
        h.start_daemon()
        h.ctl(PLAYER, "play")
        h.wait(lambda s: s["status"] == "playing" and s["lyrics"] and s["track"]["art"], 15)
        h.ctl(PLAYER, "pause")
        look = h.run / "hyde" / "encore.look"
        update_look(look, style="visual", stage_bg="clear", gradient=2)
        box, app = open_app(h, lab, "home", size=f"{WINDOW[0]} {WINDOW[1]}")
        window = dict(zip(("x", "y", "w", "h"), box, strict=True))
        time.sleep(2.0)  # fonts, the cover, the field
        h.ctl(PLAYER, "position", "0.4")
        rec = subprocess.Popen(
            ["wf-recorder", "-y", "-o", LAB, "-r", "60", "-f", str(out / "raw.mp4")],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(0.6)  # the recorder is rolling
        began = time.monotonic()
        h.ctl(PLAYER, "play")
        cuts = []
        frame = "window"
        for at, kind, value in SHOTS:
            while time.monotonic() - began < at:
                time.sleep(0.01)
            if kind == "page":
                if value != "home":
                    launch_app(h, value, f"app-{value}.log").wait(10)
                frame = "full" if value == "full" else "window"
            else:
                update_look(look, **value)
            shot = value if isinstance(value, str) else value["style"]
            cuts.append(
                {"at": round(time.monotonic() - began + 0.6, 3), "frame": frame, "shot": shot}
            )
        while time.monotonic() - began < TAKE_SECONDS:
            time.sleep(0.05)
        rec.send_signal(signal.SIGINT)
        rec.wait(15)
        app.terminate()
        # the recording began 0.6 s before the take's clock; the first shot starts there
        cuts[0]["at"] = 0.6
        (out / "cuts.json").write_text(json.dumps({"window": window, "cuts": cuts}, indent=1))
    cut(out / "raw.mp4", cuts, window, out / "clip.mp4", args.scale)
    print(out / "clip.mp4")
    return 0


if __name__ == "__main__":
    sys.exit(main())
