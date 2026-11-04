#!/usr/bin/env python3
"""encore: word-by-word synced lyrics and album colors for HyDE.

Usage (through hyde-shell):
    hyde-shell encore daemon [--if-enabled]   run the service
    hyde-shell encore status                  print the current state as JSON
    hyde-shell encore hyprlock                print the lyric line for hyprlock

The daemon follows the active MPRIS player, finds lyrics (local .lrc, LRCLIB,
Spicy Lyrics), tracks the sung word and publishes state as JSON lines on
$XDG_RUNTIME_DIR/hyde/encore.sock. Configure it in ~/.config/hyde/config.toml
under [encore].
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# HyDE's pyutils lives in $LIB_DIR/hyde; needed when encore is symlinked in from a checkout.
_hyde_lib = os.path.join(os.environ.get("LIB_DIR") or os.path.expanduser("~/.local/lib"), "hyde")
if _hyde_lib not in sys.path:
    sys.path.append(_hyde_lib)

import pyutils.logger as hyde_logger
from encorelib.cache import LyricsCache
from encorelib.clock import PlaybackClock
from encorelib.config import EncoreConfig, load_config
from encorelib.lookup import lookup_lyrics
from encorelib.palette import album_palette, cover_png, fetch_art, wallpaper_palette
from encorelib.protocol import (
    StateServer,
    build_state,
    hyprlock_colors,
    hyprlock_markup,
    hyprlock_track,
    read_state,
)
from encorelib.providers import TrackInfo, track_key
from encorelib.session import (
    FetchGate,
    guarded,
    micros_to_seconds,
    order_by_recency,
    pick_player,
)
from encorelib.timing import NO_CURSOR, locate, with_words
from pyutils.xdg_base_dirs import xdg_cache_home, xdg_runtime_dir

logger = hyde_logger.get_logger()
log = logging.getLogger("encore")  # errors always reach stderr / the journal

RUNTIME_DIR = (xdg_runtime_dir() or Path(f"/run/user/{os.getuid()}")) / "hyde"
SOCKET_PATH = RUNTIME_DIR / "encore.sock"
HYPRLOCK_PATH = RUNTIME_DIR / "encore.hyprlock"
TRACK_PATH = RUNTIME_DIR / "encore.track"  # title and artist lines for hyprlock
OVERLAY_PIDFILE = RUNTIME_DIR / "encore-overlay.pid"
LOOK_PATH = RUNTIME_DIR / "encore.look"
GLOW_PIDFILE = RUNTIME_DIR / "encore-glow.pid"
PLAYER_PIDFILE = RUNTIME_DIR / "encore-player.pid"
COVER_PATH = RUNTIME_DIR / "encore.cover.png"  # album art for hyprlock
RUNTIME_FILES = (HYPRLOCK_PATH, TRACK_PATH, COVER_PATH)
CACHE_DIR = xdg_cache_home() / "hyde" / "encore"

TICK_MS = 50
RESYNC_TICKS = 20  # resync the clock with the player every second


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


class Encore:
    def __init__(self, cfg: EncoreConfig, server: StateServer):
        import gi

        gi.require_version("Playerctl", "2.0")
        from gi.repository import GLib, Playerctl

        self.GLib = GLib
        self.Playerctl = Playerctl
        self.cfg = cfg
        self.server = server
        self.cache = LyricsCache(CACHE_DIR)
        self.clock = PlaybackClock()
        self.lyrics_gate = FetchGate()
        self.palette_gate = FetchGate()
        self.player = None
        self.track: TrackInfo | None = None
        self.art_url = ""
        self.lyrics = None
        self.art: Path | None = None
        self.palette: dict[str, str] = wallpaper_palette()
        self.shown_cover: Path | None = None
        self.tick_id = 0
        self.ticks = 0
        self.recent: list[str] = []
        self.last_cursor = None

        self.manager = Playerctl.PlayerManager()
        self.manager.connect("name-appeared", self.on_name_appeared)
        self.manager.connect("player-vanished", self.on_player_vanished)
        for name in self.manager.props.player_names:
            self.add_player(name)
        self.choose_player()

    # players -------------------------------------------------------------

    @guarded()
    def add_player(self, name) -> None:
        player = self.Playerctl.Player.new_from_name(name)
        player.connect("playback-status", self.on_status)
        player.connect("metadata", self.on_metadata)
        player.connect("seeked", self.on_seeked)
        self.manager.manage_player(player)

    @guarded()
    def on_name_appeared(self, _manager, name) -> None:
        self.add_player(name)
        self.choose_player()

    def is_current(self, player) -> bool:
        return (
            self.player is not None
            and player.props.player_instance == self.player.props.player_instance
        )

    @guarded()
    def on_player_vanished(self, _manager, player) -> None:
        if self.is_current(player):
            self.player = None
        self.choose_player()

    def status_of(self, player) -> str:
        return player.props.playback_status.value_nick

    def choose_player(self) -> None:
        players = {p.props.player_instance: p for p in self.manager.props.players}
        order = order_by_recency(list(players), self.recent)
        name = pick_player(
            [(inst, self.status_of(players[inst])) for inst in order], self.cfg.players
        )
        chosen = players.get(name) if name else None
        if chosen is None or not self.is_current(chosen):
            if chosen is not None or self.player is not None:
                logger.info(f"encore follows {name}")
            self.player = chosen
        self.refresh_track()
        self.refresh_playback()

    @guarded()
    def on_status(self, player, _status) -> None:
        instance = player.props.player_instance
        if self.status_of(player) == "Playing":
            self.recent = [instance] + [i for i in self.recent if i != instance]
        self.choose_player()

    @guarded()
    def on_metadata(self, player, _metadata) -> None:
        if self.is_current(player):
            self.refresh_track()
            self.refresh_playback()

    @guarded()
    def on_seeked(self, player, position) -> None:
        if self.is_current(player):
            self.clock.sync(micros_to_seconds(position), self.clock.playing)
            self.last_cursor = None
            self.publish()

    # track and lyrics ------------------------------------------------------

    def read_track(self) -> tuple[TrackInfo, str] | None:
        if self.player is None:
            return None
        md = self.player.props.metadata
        md = md.unpack() if md is not None else {}
        title = self.player.get_title() or ""
        if not title:
            return None
        info = TrackInfo(
            title=title,
            artist=self.player.get_artist() or "",
            album=self.player.get_album() or "",
            length=micros_to_seconds(md.get("mpris:length")),
            url=str(md.get("xesam:url") or ""),
            trackid=str(md.get("mpris:trackid") or ""),
            player=self.player.props.player_name,
        )
        return info, str(md.get("mpris:artUrl") or "")

    def refresh_track(self) -> None:
        found = self.read_track()
        if found is None:
            if self.track is not None:
                self.track, self.lyrics, self.art = None, None, None
                self.lyrics_gate.begin("")
                self.palette_gate.begin("")
            return
        info, art_url = found
        if self.track is not None and track_key(info) == track_key(self.track):
            if art_url != self.art_url:
                self.art_url = art_url
                self.start_palette(info, art_url)
            return
        self.track, self.art_url = info, art_url
        self.lyrics, self.art, self.last_cursor = None, None, None
        token = self.lyrics_gate.begin(track_key(info))
        threading.Thread(target=self.fetch_lyrics, args=(info, token), daemon=True).start()
        self.start_palette(info, art_url)

    def fetch_lyrics(self, info: TrackInfo, token: int) -> None:
        """Worker thread: always reports back, even when a lookup blows up."""
        key = track_key(info)
        lyrics = None
        try:
            lyrics = lookup_lyrics(info, self.cfg, self.cache)
            if lyrics is not None:
                lyrics = with_words(lyrics)
        except Exception:
            log.exception("lyrics lookup failed")
            lyrics = None
        self.GLib.idle_add(self.apply_lyrics, token, key, lyrics)

    def apply_lyrics(self, token: int, key: str, lyrics) -> bool:
        if self.lyrics_gate.accept(token, key):
            source = lyrics.source if lyrics else "none"
            logger.info(f"lyrics: {source}")
            self.lyrics = lyrics
            self.last_cursor = None
            self.publish()
        return False

    def start_palette(self, info: TrackInfo, art_url: str) -> None:
        token = self.palette_gate.begin(track_key(info))

        def work():
            art, palette = None, {}
            try:
                original = fetch_art(art_url, CACHE_DIR / "art")
                if original:
                    palette = album_palette(original, CACHE_DIR / "palette")
                    art = cover_png(original, CACHE_DIR / "covers") or original
            except Exception:
                log.exception("album palette failed")
            self.GLib.idle_add(self.apply_palette, token, track_key(info), art, palette)

        threading.Thread(target=work, daemon=True).start()

    def apply_palette(self, token: int, key: str, art, palette) -> bool:
        if self.palette_gate.accept(token, key):
            self.art = art
            self.palette = palette or wallpaper_palette()
            self.last_cursor = None
            self.publish()
        return False

    # playback clock ------------------------------------------------------

    def player_position(self) -> float:
        try:
            return self.player.get_position() / 1e6
        except self.GLib.Error:
            return self.clock.position()

    def refresh_playback(self) -> None:
        playing = self.player is not None and self.status_of(self.player) == "Playing"
        position = self.player_position() if self.player is not None else 0.0
        self.clock.sync(position, playing)
        if playing and not self.tick_id:
            self.tick_id = self.GLib.timeout_add(TICK_MS, self.tick)
        elif not playing and self.tick_id:
            self.GLib.source_remove(self.tick_id)
            self.tick_id = 0
        self.last_cursor = None
        self.publish()

    @guarded(default=True)
    def tick(self) -> bool:
        self.ticks += 1
        if self.ticks % RESYNC_TICKS == 0 and self.player is not None:
            self.clock.sync(self.player_position(), True)
            self.publish()
            return True
        cursor = locate(self.lyrics, self.clock.position()) if self.lyrics else NO_CURSOR
        if (cursor.line, cursor.word) != self.last_cursor:
            self.publish()
        return True

    # output ----------------------------------------------------------------

    def status(self) -> str:
        if self.player is None or self.track is None:
            return "stopped"
        return "playing" if self.clock.playing else "paused"

    def show_cover(self) -> None:
        """Keep COVER_PATH in step with the current track's art (copied, so hyprlock
        sees a new mtime); removed while there is no art so the layout falls back."""
        cover = self.art if self.track is not None else None
        if cover == self.shown_cover:
            return
        self.shown_cover = cover
        if cover is None:
            COVER_PATH.unlink(missing_ok=True)
            return
        tmp = COVER_PATH.with_suffix(".tmp.png")
        shutil.copyfile(cover, tmp)
        os.replace(tmp, COVER_PATH)

    def publish(self) -> None:
        cursor = locate(self.lyrics, self.clock.position()) if self.lyrics else NO_CURSOR
        self.last_cursor = (cursor.line, cursor.word)
        accent, dim = hyprlock_colors(self.cfg, self.palette)
        markup = hyprlock_markup(self.lyrics, cursor, accent, dim) if self.track else ""
        write_atomic(HYPRLOCK_PATH, markup + "\n" if markup else "")
        write_atomic(TRACK_PATH, hyprlock_track(self.track))
        self.show_cover()
        self.server.broadcast(
            build_state(self.status(), self.track, self.art, self.lyrics, self.clock, self.palette)
        )


def spawn_overlay() -> None:
    """Start the overlay as its own detached process via encore.sh (LD_PRELOAD)."""
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "encore.sh")
    subprocess.Popen(
        ["bash", script, "overlay"],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def ensure_daemon() -> None:
    """Start the encore service when a surface opens and none is answering."""
    from encorelib.service import ensure_daemon as ensure

    def run_directly() -> None:
        subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), "daemon"],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    ensure(SOCKET_PATH, os.environ.get("XDG_SESSION_DESKTOP", ""), fallback=run_directly)


def run_overlay_cmd() -> int:
    os.environ.setdefault("GSK_RENDERER", "cairo")
    from encorelib import single

    if not single.claim(OVERLAY_PIDFILE):
        print("encore overlay is already running", file=sys.stderr)
        return 0
    try:
        from encoregui.overlay import run_overlay

        return run_overlay(load_config(), str(RUNTIME_DIR))
    finally:
        single.release(OVERLAY_PIDFILE)


def run_toggle() -> int:
    from encorelib import single

    pid = single.read_pid(OVERLAY_PIDFILE)
    if pid is not None and single.pid_alive(pid):
        os.kill(pid, signal.SIGTERM)
        print("encore overlay hidden")
        return 0
    ensure_daemon()
    spawn_overlay()
    print("encore overlay shown")
    return 0


def run_glow_cmd() -> int:
    # the glow is GPU-scaled textures: GTK's default GL renderer suits it
    # (the overlay keeps cairo, where small text surfaces win)
    from encorelib import single

    if not single.claim(GLOW_PIDFILE):
        print("encore glow is already running", file=sys.stderr)
        return 0
    try:
        from encoregui.glow import run_glow

        return run_glow(load_config(), str(RUNTIME_DIR))
    finally:
        single.release(GLOW_PIDFILE)


def run_glow_toggle() -> int:
    from encorelib import single

    pid = single.read_pid(GLOW_PIDFILE)
    if pid is not None and single.pid_alive(pid):
        os.kill(pid, signal.SIGTERM)
        print("encore glow off")
        return 0
    ensure_daemon()
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "encore.sh")
    subprocess.Popen(
        ["bash", script, "glow", "--run"],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print("encore glow on")
    return 0


def run_player_cmd(start: str = "player") -> int:
    from encoregui.player import run_player

    ensure_daemon()
    return run_player(str(RUNTIME_DIR), str(PLAYER_PIDFILE), start)


def _ensure(pidfile: Path, command: list[str], want_on: bool) -> None:
    from encorelib import single

    pid = single.read_pid(pidfile)
    running = pid is not None and single.pid_alive(pid)
    if running != want_on:
        subprocess.run(command, check=False, stdout=subprocess.DEVNULL)


def run_profile(name: str) -> int:
    from encorelib.profiles import PROFILES, apply_profile

    glow = apply_profile(LOOK_PATH, name)
    if glow is None:
        print(f"unknown profile {name!r}; one of: {', '.join(PROFILES)}", file=sys.stderr)
        return 1
    me = [sys.executable, os.path.abspath(__file__)]
    _ensure(GLOW_PIDFILE, [*me, "glow"], glow)
    _ensure(OVERLAY_PIDFILE, [*me, "toggle"], True)
    print(f"profile {name}")
    return 0


def run_show() -> int:
    """Toggle the show workspace: an empty stage with the full show running."""
    from encorelib.profiles import SHOW_WORKSPACE, show_action

    try:
        active = json.loads(
            subprocess.run(
                ["hyprctl", "activeworkspace", "-j"], capture_output=True, text=True, check=True
            ).stdout
        ).get("name", "")
    except (OSError, ValueError, subprocess.CalledProcessError):
        active = ""
    if show_action(active) == "enter":
        subprocess.run(
            ["hyprctl", "dispatch", "workspace", f"name:{SHOW_WORKSPACE}"],
            check=False,
            stdout=subprocess.DEVNULL,
        )
        return run_profile("show")
    subprocess.run(
        ["hyprctl", "dispatch", "workspace", "previous"], check=False, stdout=subprocess.DEVNULL
    )
    return run_profile("working")


def run_style(name: str) -> int:
    name = name.strip().lower()
    from encorelib.look import read_look, update_look
    from encorelib.stream import STYLES

    current = read_look(LOOK_PATH).get("style") or load_config().overlay_style
    if name == "next":
        name = STYLES[(STYLES.index(current) + 1) % len(STYLES)]
    if name not in STYLES:
        print(f"unknown style {name!r}; one of: {', '.join(STYLES)}", file=sys.stderr)
        return 1
    update_look(LOOK_PATH, style=name)
    print(name)
    return 0


def run_look(key: str, value: str) -> int:
    from encorelib.look import MAX_SIZE, MIN_SIZE, update_look

    if key == "reset":
        update_look(
            LOOK_PATH, style=None, font=None, size=None, color=None, next_line=None, motion=None
        )
        print("look reset to config")
        return 0
    change: dict
    if key == "font":
        change = {"font": value}
    elif key == "size":
        try:
            change = {"size": int(value)}
        except ValueError:
            print(f"size must be {MIN_SIZE}-{MAX_SIZE}", file=sys.stderr)
            return 1
    elif key == "color":
        change = {"color": None if value.lower() == "auto" else value}
    elif key == "next-line":
        change = {"next_line": value.lower() in ("1", "true", "on", "yes")}
    elif key == "motion":
        change = {"motion": value.lower() in ("1", "true", "on", "yes")}
    else:
        print("usage: encore look font|size|color|next-line|reset [value]", file=sys.stderr)
        return 1
    before = dict(change)
    after = update_look(LOOK_PATH, **change)
    for k, v in before.items():
        if v is not None and after.get(k) != v:
            print(f"rejected {k}={v!r}", file=sys.stderr)
            return 1
    print(json.dumps(after))
    return 0


def _rofi(entries: list[str], prompt: str, index: bool = False) -> str:
    """Run a rofi dmenu; with index=True the selected row NUMBER is returned."""
    cmd = ["rofi", "-dmenu", "-i", "-p", prompt]
    if index:
        cmd += ["-format", "i"]
    try:
        result = subprocess.run(
            cmd, input="\n".join(entries), capture_output=True, text=True, check=False
        )
    except FileNotFoundError:
        print("encore menu needs rofi", file=sys.stderr)
        return ""
    return result.stdout.strip()


def run_menu() -> int:
    """The encore control menu: playback, style, font, size, color, toggles."""
    from encorelib.look import read_look, update_look
    from encorelib.protocol import read_state
    from encorelib.stream import STYLES

    while True:
        look = read_look(LOOK_PATH)
        state = read_state(SOCKET_PATH) or {}
        track = state.get("track") or {}
        now = f"{track.get('title', '')} - {track.get('artist', '')}".strip(" -")
        style = look.get("style") or load_config().overlay_style
        entries = [
            f"Play / Pause{('   (' + now + ')') if now else ''}",
            "Next track",
            "Previous track",
            f"Style: {style}",
            f"Font: {look.get('font', 'config')}",
            f"Size: {look.get('size', 'config')}",
            f"Color: {look.get('color', 'auto')}",
            f"Motion: {'on' if look.get('motion', True) else 'off'}",
            "Lyrics on/off",
            "Glow on/off",
            f"Player: {state.get('player') or 'auto'}",
            "Reset look",
        ]
        picked = _rofi(entries, "encore", index=True)
        try:
            row = int(picked)
        except ValueError:
            return 0
        if row == 0:
            subprocess.run(["playerctl", "play-pause"], check=False)
        elif row == 1:
            subprocess.run(["playerctl", "next"], check=False)
        elif row == 2:
            subprocess.run(["playerctl", "previous"], check=False)
        elif row == 3:
            pick = _rofi(list(STYLES), "style")
            if pick:
                run_style(pick)
        elif row == 4:
            fonts = subprocess.run(
                ["fc-list", ":", "family"], capture_output=True, text=True, check=False
            ).stdout
            families = sorted(
                {line.split(",")[0].strip() for line in fonts.splitlines() if line.strip()}
            )
            pick = _rofi(families, "font")
            if pick:
                update_look(LOOK_PATH, font=pick)
        elif row == 5:
            pick = _rofi([str(n) for n in range(18, 58, 4)], "size")
            if pick.isdigit():
                update_look(LOOK_PATH, size=int(pick))
        elif row == 6:
            palette = state.get("palette") or {}
            swatches = ["auto"] + [
                f"#{palette[k]}  ({k})"
                for k in ("1xa8", "2xa8", "3xa8", "4xa8", "txt1")
                if k in palette
            ]
            pick = _rofi(swatches, "color (hex or auto)")
            if pick:
                update_look(LOOK_PATH, color=None if pick == "auto" else pick.split()[0])
        elif row == 7:
            update_look(LOOK_PATH, motion=not look.get("motion", True))
        elif row == 8:
            run_toggle()
        elif row == 9:
            run_glow_toggle()
        elif row == 10:
            players = subprocess.run(
                ["playerctl", "--list-all"], capture_output=True, text=True, check=False
            ).stdout.split()
            pick = _rofi(players, "give encore this player")
            if pick:
                subprocess.run(["playerctl", "-p", pick, "play"], check=False)
        elif row == 11:
            update_look(
                LOOK_PATH,
                style=None,
                font=None,
                size=None,
                color=None,
                next_line=None,
                motion=None,
            )
        else:
            return 0


def run_daemon(if_enabled: bool) -> int:
    from gi.repository import GLib

    logging.basicConfig(stream=sys.stderr, level=logging.WARNING, format="encore: %(message)s")
    cfg = load_config()
    if if_enabled and not cfg.enable:
        return 0
    server = StateServer(SOCKET_PATH)
    try:
        server.start()
    except RuntimeError:
        print("encore is already running", file=sys.stderr)
        return 0

    loop = GLib.MainLoop()

    def on_client(_fd, _condition) -> bool:
        server.accept()
        return True

    GLib.io_add_watch(server.sock.fileno(), GLib.IO_IN, on_client)
    try:
        from gi.repository import GLibUnix

        signal_add = GLibUnix.signal_add
    except ImportError:  # PyGObject < 3.52
        signal_add = GLib.unix_signal_add
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal_add(GLib.PRIORITY_DEFAULT, sig, loop.quit)

    try:
        Encore(cfg, server)
        if cfg.overlay_enable:
            spawn_overlay()
        loop.run()
    finally:
        server.close()
        for path in RUNTIME_FILES:
            path.unlink(missing_ok=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="encore", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    daemon = sub.add_parser("daemon", help="run the encore service")
    daemon.add_argument(
        "--if-enabled", action="store_true", help="exit unless [encore] enable = true"
    )
    sub.add_parser("overlay", help="run the lyrics overlay (started via encore.sh)")
    sub.add_parser("toggle", help="show or hide the lyrics overlay")
    glow = sub.add_parser("glow", help="toggle the screen-edge glow")
    glow.add_argument("--run", action="store_true", help="run the glow process in the foreground")
    style = sub.add_parser("style", help="switch the overlay style (line, stack, constellation)")
    style.add_argument("name", nargs="?", default="next", help="style name, or 'next' to cycle")
    look = sub.add_parser(
        "look", help="change the overlay look live (font, size, color, next-line, reset)"
    )
    look.add_argument("key", help="font | size | color | next-line | motion | reset")
    look.add_argument("value", nargs="?", default="", help="new value ('auto' for color resets it)")
    menu = sub.add_parser("menu", help="open the encore player window")
    menu.add_argument("--rofi", action="store_true", help="use the compact rofi menu instead")
    player = sub.add_parser("player", help="open the encore player window")
    player.add_argument(
        "--open",
        choices=("player", "lyrics", "look", "glow"),
        default="player",
        help="start in lyrics view, or with the look menu or glow settings open",
    )
    profile = sub.add_parser("profile", help="apply a sound setup: working or show")
    profile.add_argument("name", help="working | show")
    sub.add_parser("show", help="toggle the show workspace (full show on an empty stage)")
    sub.add_parser("status", help="print the current state as JSON")
    sub.add_parser("hyprlock", help="print the current lyric line as Pango markup")
    args = parser.parse_args(argv)

    if args.command == "daemon":
        return run_daemon(args.if_enabled)
    if args.command == "overlay":
        return run_overlay_cmd()
    if args.command == "toggle":
        return run_toggle()
    if args.command == "style":
        return run_style(args.name)
    if args.command == "look":
        return run_look(args.key, args.value)
    if args.command == "menu":
        return run_menu() if args.rofi else run_player_cmd()
    if args.command == "player":
        return run_player_cmd(args.open)
    if args.command == "profile":
        return run_profile(args.name)
    if args.command == "show":
        return run_show()
    if args.command == "glow":
        return run_glow_cmd() if args.run else run_glow_toggle()
    if args.command == "status":
        print(json.dumps(read_state(SOCKET_PATH) or {"status": "stopped"}, ensure_ascii=False))
        return 0
    if args.command == "hyprlock":
        try:
            sys.stdout.write(HYPRLOCK_PATH.read_text(encoding="utf-8"))
        except OSError:
            pass
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
