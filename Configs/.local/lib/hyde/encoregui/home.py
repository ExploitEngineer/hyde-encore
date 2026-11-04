"""The Home and Lyrics pages of the Encore window, after the reference player.

Home: the cover with an album-tinted halo (it grows on hover), title and
artist, a seek bar, round transport controls, the Lyrics pill and the
volume. With nothing playing it shows an idle message and buttons for the
music apps that are installed. Lyrics: a card with a smaller cover and the
controls on the left, the lines on the right with the current one bright;
clicking a line seeks there.
"""

from __future__ import annotations

import re
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib, Gtk

from encoregui.cover import CoverView
from encoregui.lyriclist import LyricList
from encoregui.ui import icon_button, icon_image, set_icon
from encorelib.journal import read_lines
from encorelib.lyricview import live_position
from encorelib.screen import lookup_reason, pick_music_apps, screen_state
from encorelib.transport import fmt_time

ART = 256
ART_EXPANDED = 320
EXPAND_MS = 220
PAUSED_ALPHA = 0.85
SEEK_DEBOUNCE_MS = 150
VOLUME_DEBOUNCE_MS = 80
HOLD_AFTER_INPUT = 1.0  # seconds the user's own value wins over the state's
PAD_MESSAGE = 6


def cover_path(state: dict) -> str:
    """The best cover in a state: the full-size one, else the lock-screen copy."""
    track = state.get("track") or {}
    return track.get("cover") or track.get("art") or ""


def meta_labels() -> tuple[Gtk.Label, Gtk.Label]:
    title = Gtk.Label(label="Nothing playing")
    title.add_css_class("title")
    title.set_ellipsize(3)
    title.set_max_width_chars(34)
    title.set_width_chars(34)  # a long title never widens the window
    artist = Gtk.Label(label="")
    artist.add_css_class("artist")
    artist.set_ellipsize(3)
    artist.set_max_width_chars(40)
    artist.set_width_chars(40)
    return title, artist


def set_meta(title: Gtk.Label, artist: Gtk.Label, state: dict) -> None:
    track = state.get("track") or {}
    for label, value in (
        (title, track.get("title") or "Nothing playing"),
        (artist, track.get("artist") or ""),
    ):
        if label.get_label() != value:
            label.set_label(value)
            label.set_tooltip_text(value or None)  # the whole text when it is cut


class Transport(Gtk.Box):
    """Back 15 s, previous, play/pause, next, forward 15 s."""

    def __init__(self, win):
        super().__init__(spacing=12)
        self.set_halign(Gtk.Align.CENTER)
        self.play = icon_button(
            "media-playback-start-symbolic",
            lambda *_: win.ctl("play-pause"),
            big=True,
            tooltip="Play or pause (Space)",
        )
        self.play_icon = ""
        for widget in (
            icon_button(
                "media-seek-backward-symbolic", lambda *_: win.seek(-15), tooltip="Back 15 s"
            ),
            icon_button(
                "media-skip-backward-symbolic",
                lambda *_: win.ctl("previous"),
                tooltip="Previous (P)",
            ),
            self.play,
            icon_button(
                "media-skip-forward-symbolic", lambda *_: win.ctl("next"), tooltip="Next (N)"
            ),
            icon_button(
                "media-seek-forward-symbolic", lambda *_: win.seek(15), tooltip="Forward 15 s"
            ),
        ):
            widget.set_valign(Gtk.Align.CENTER)
            self.append(widget)

    def update(self, state: dict) -> None:
        icon = (
            "media-playback-pause-symbolic"
            if state.get("status") == "playing"
            else "media-playback-start-symbolic"
        )
        if icon != self.play_icon:
            self.play_icon = icon
            set_icon(self.play.get_child(), icon)


class SeekBar(Gtk.Box):
    """Elapsed time, the position slider and the length; dragging seeks."""

    def __init__(self, win, width: int = 380):
        super().__init__(spacing=10)
        self.win = win
        self.set_halign(Gtk.Align.CENTER)
        self.elapsed = Gtk.Label(label="0:00")
        self.total = Gtk.Label(label="0:00")
        for label in (self.elapsed, self.total):
            label.add_css_class("time")
            label.set_width_chars(5)
        self.elapsed.set_xalign(1.0)
        self.total.set_xalign(0.0)
        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1, 1)
        self.scale.add_css_class("seek")
        self.scale.set_draw_value(False)
        self.scale.set_size_request(width, -1)
        self.scale.connect("change-value", self._on_change)
        self.append(self.elapsed)
        self.append(self.scale)
        self.append(self.total)
        self.state: dict = {}
        self.held_until = 0.0
        self.pending: float | None = None
        self.debounce = 0
        self.timer = 0

    def update(self, state: dict) -> None:
        self.state = state
        length = float((state.get("track") or {}).get("length") or 0)
        self.set_visible(length > 0)
        if length > 0:
            self.scale.set_range(0, length)
            self.total.set_label(fmt_time(length))
        self._show_position()
        playing = state.get("status") == "playing" and length > 0
        if playing and not self.timer:
            self.timer = GLib.timeout_add(250, self._tick)
        elif not playing and self.timer:
            GLib.source_remove(self.timer)
            self.timer = 0

    def _tick(self) -> bool:
        if not self.get_mapped():
            return True  # cheap while hidden: nothing is drawn
        self._show_position()
        return True

    def _show_position(self) -> None:
        if time.monotonic() < self.held_until:
            return
        position = live_position(self.state, time.monotonic()) if self.state else 0.0
        self.scale.set_value(position)
        self.elapsed.set_label(fmt_time(position))

    def _on_change(self, _scale, _scroll, value) -> bool:
        self.held_until = time.monotonic() + HOLD_AFTER_INPUT
        self.pending = max(0.0, value)
        self.elapsed.set_label(fmt_time(self.pending))
        if self.debounce:
            GLib.source_remove(self.debounce)
        self.debounce = GLib.timeout_add(SEEK_DEBOUNCE_MS, self._commit)
        return False

    def _commit(self) -> bool:
        self.debounce = 0
        if self.pending is not None:
            self.win.seek_to(self.pending)
            self.pending = None
        return False


class VolumeControl(Gtk.Box):
    """A speaker and a slider for the followed player's volume; hidden when it has none."""

    def __init__(self, win):
        super().__init__(spacing=8)
        self.win = win
        self.icon = icon_image("audio-volume-high-symbolic")
        self.icon.set_pixel_size(16)
        self.icon.add_css_class("dim-icon")
        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1, 0.01)
        self.scale.add_css_class("volume")
        self.scale.set_draw_value(False)
        self.scale.set_size_request(140, -1)
        self.scale.set_tooltip_text("Volume (Up and Down)")
        self.scale.connect("change-value", self._on_change)
        self.append(self.icon)
        self.append(self.scale)
        self.held_until = 0.0
        self.pending: float | None = None
        self.debounce = 0
        self.icon_name = ""

    def update(self, state: dict) -> None:
        volume = state.get("volume")
        self.set_visible(volume is not None)
        if volume is None or time.monotonic() < self.held_until:
            return
        self.scale.set_value(volume)
        self._set_icon(volume)

    def _set_icon(self, volume: float) -> None:
        name = (
            "audio-volume-muted-symbolic"
            if volume <= 0.001
            else "audio-volume-low-symbolic"
            if volume < 0.34
            else "audio-volume-medium-symbolic"
            if volume < 0.67
            else "audio-volume-high-symbolic"
        )
        if name != self.icon_name:
            self.icon_name = name
            set_icon(self.icon, name)

    def _on_change(self, _scale, _scroll, value) -> bool:
        self.held_until = time.monotonic() + HOLD_AFTER_INPUT
        self.pending = min(1.0, max(0.0, value))
        self._set_icon(self.pending)
        if self.debounce:
            GLib.source_remove(self.debounce)
        self.debounce = GLib.timeout_add(VOLUME_DEBOUNCE_MS, self._commit)
        return False

    def _commit(self) -> bool:
        self.debounce = 0
        if self.pending is not None:
            self.win.set_volume(self.pending)
            self.pending = None
        return False


def lyrics_pill(win, on: bool = False) -> Gtk.Button:
    pill = Gtk.Button()
    pill.add_css_class("pill")
    if on:
        pill.add_css_class("on")
    box = Gtk.Box(spacing=6)
    icon = icon_image("chat-message-new-symbolic")
    icon.set_pixel_size(14)
    box.append(icon)
    box.append(Gtk.Label(label="Lyrics"))
    pill.set_child(box)
    pill.set_tooltip_text("Lyrics (L)")
    pill.connect("clicked", lambda *_: win.toggle_lyrics())
    return pill


def app_name(name: str) -> str:
    """ "Spotify (Launcher)" -> "Spotify": the parenthetical is packaging detail."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", name).strip() or name


def music_apps() -> list[Gio.AppInfo]:
    """Installed music apps worth offering when nothing plays."""
    infos = {info.get_id(): info for info in Gio.AppInfo.get_all() if info.should_show()}
    rows = [
        (app_id, info.get_name(), getattr(info, "get_categories", lambda: "")() or "")
        for app_id, info in infos.items()
        if app_id
    ]
    return [infos[app_id] for app_id in pick_music_apps(rows)]


class HomePage(Gtk.Stack):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.set_transition_duration(300)
        self.expanded = 0.0  # 0..1 cover hover expansion
        self.expand_target = 0.0
        self.expand_timer = 0
        self.add_named(self._build_player(win), "player")
        self.add_named(self._build_idle(win), "idle")

    def _build_player(self, win) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        page.set_valign(Gtk.Align.CENTER)
        page.set_halign(Gtk.Align.CENTER)
        self.cover = CoverView(ART)
        self.cover.set_halign(Gtk.Align.CENTER)
        motion = Gtk.EventControllerMotion()
        motion.connect("enter", lambda *_: self._expand(1.0))
        motion.connect("leave", lambda *_: self._expand(0.0))
        self.cover.add_controller(motion)
        page.append(self.cover)
        self.title, self.artist = meta_labels()
        self.title.set_margin_top(6)
        page.append(self.title)
        page.append(self.artist)
        self.seek = SeekBar(win)
        self.seek.set_margin_top(6)
        page.append(self.seek)
        self.transport = Transport(win)
        page.append(self.transport)
        row = Gtk.Box(spacing=18)
        row.set_halign(Gtk.Align.CENTER)
        row.set_margin_top(4)
        row.append(lyrics_pill(win))
        self.volume = VolumeControl(win)
        self.volume.set_valign(Gtk.Align.CENTER)
        row.append(self.volume)
        page.append(row)
        return page

    def _build_idle(self, win) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        page.set_valign(Gtk.Align.CENTER)
        page.set_halign(Gtk.Align.CENTER)
        title = Gtk.Label(label="Nothing playing")
        title.add_css_class("idle-title")
        hint = Gtk.Label(label="Play a song in any player and Encore follows it.")
        hint.add_css_class("artist")
        page.append(title)
        page.append(hint)
        self.apps = Gtk.Box(spacing=10)
        self.apps.set_halign(Gtk.Align.CENTER)
        self.apps.set_margin_top(14)
        page.append(self.apps)
        page.connect("map", lambda *_: self._fill_apps())
        return page

    def _fill_apps(self) -> None:
        child = self.apps.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.apps.remove(child)
            child = nxt
        for info in music_apps():
            button = Gtk.Button()
            button.add_css_class("pill")
            box = Gtk.Box(spacing=8)
            icon = info.get_icon()
            if icon is not None:
                image = Gtk.Image.new_from_gicon(icon)
                image.set_pixel_size(18)
                box.append(image)
            box.append(Gtk.Label(label=f"Open {app_name(info.get_name())}"))
            button.set_child(box)
            button.connect("clicked", lambda _b, i=info: i.launch([], None))
            self.apps.append(button)

    def update(self, state: dict, _colors) -> None:
        idle = screen_state(state, time.monotonic()) == "idle"
        self.set_visible_child_name("idle" if idle else "player")
        if idle:
            return
        set_meta(self.title, self.artist, state)
        self.seek.update(state)
        self.transport.update(state)
        self.volume.update(state)
        self.cover.set_path(cover_path(state))
        self.cover.set_alpha(PAUSED_ALPHA if state.get("status") == "paused" else 1.0)

    def _expand(self, target: float) -> None:
        self.expand_target = target
        if not self.expand_timer:
            self.expand_timer = GLib.timeout_add(16, self._expand_step)

    def _expand_step(self) -> bool:
        step = 16 / EXPAND_MS
        if self.expanded < self.expand_target:
            self.expanded = min(self.expand_target, self.expanded + step)
        else:
            self.expanded = max(self.expand_target, self.expanded - step)
        eased = 1 - (1 - self.expanded) ** 3
        self.cover.set_side(int(ART + (ART_EXPANDED - ART) * eased))
        self.win.field.set_hover(eased)
        if self.expanded == self.expand_target:
            self.expand_timer = 0
            return False
        return True


class LyricsPage(Gtk.Box):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.set_valign(Gtk.Align.CENTER)
        self.set_halign(Gtk.Align.CENTER)
        self.key = ""
        card = Gtk.Box(spacing=28)
        card.add_css_class("card")
        card.set_size_request(820, 380)
        self.append(card)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        left.set_valign(Gtk.Align.CENTER)
        self.cover = CoverView(210)
        self.cover.set_halign(Gtk.Align.CENTER)
        left.append(self.cover)
        self.title, self.artist = meta_labels()
        self.title.set_width_chars(24)
        self.title.set_max_width_chars(24)
        self.artist.set_width_chars(28)
        self.artist.set_max_width_chars(28)
        left.append(self.title)
        left.append(self.artist)
        self.seek = SeekBar(win, width=190)
        left.append(self.seek)
        self.transport = Transport(win)
        left.append(self.transport)
        row = Gtk.Box(spacing=8)
        row.set_halign(Gtk.Align.CENTER)
        row.append(lyrics_pill(win, on=True))
        row.append(
            icon_button(
                "document-open-recent-symbolic",
                lambda *_: self.scroll_to_current(True),
                tooltip="Back to the current line",
            )
        )
        left.append(row)
        card.append(left)
        sep = Gtk.Box()
        sep.add_css_class("vsep")
        card.append(sep)
        self.right = Gtk.Stack()
        self.right.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.right.set_transition_duration(220)
        self.right.set_hexpand(True)
        self.list = LyricList(win.cfg.overlay_font.split(",")[0].strip() or "SF Pro Display")
        self.list.on_seek = win.seek_to
        self.right.add_named(self.list, "list")
        self.message = Gtk.Label(label="", xalign=0)
        self.message.add_css_class("lyric")
        self.message.add_css_class("message")
        self.message.set_wrap(True)
        self.message.set_max_width_chars(36)
        self.message.set_valign(Gtk.Align.CENTER)
        self.message.set_margin_start(PAD_MESSAGE)
        self.right.add_named(self.message, "message")
        card.append(self.right)

    def update(self, state: dict, colors) -> None:
        set_meta(self.title, self.artist, state)
        self.seek.update(state)
        self.transport.update(state)
        self.cover.set_path(cover_path(state))
        self.cover.set_alpha(PAUSED_ALPHA if state.get("status") == "paused" else 1.0)
        self.list.set_colors(colors)
        self._sync_lines(state)

    def _sync_lines(self, state: dict) -> None:
        mode = screen_state(state, time.monotonic())
        track = state.get("track") or {}
        lyrics = state.get("lyrics") or {}
        if mode in ("lyrics", "plain"):
            self.list.set_lines(
                lyrics.get("lines") or [], f"{track.get('key', '')}:{mode}", plain=mode == "plain"
            )
            self.list.set_state(state)
            self.right.set_visible_child_name("list")
            return
        if mode == "idle":
            text = "Nothing playing."
        elif mode == "waiting":
            text = "Looking for lyrics…"
        else:
            journal = read_lines(self.win.journal_path)
            text = lookup_reason(journal, track.get("artist") or "", track.get("title") or "")
        if self.message.get_label() != text:
            self.message.set_label(text)
        self.right.set_visible_child_name("message")

    def scroll_to_current(self, instant: bool) -> None:
        self.list.scroll_to_current(instant)
