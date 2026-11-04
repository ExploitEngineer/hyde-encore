"""The Home and Lyrics pages of the Encore window, after the reference player.

Home: the cover with an album-tinted halo (it grows on hover), title and
artist, round transport controls and a Lyrics pill. Lyrics: a card with a
smaller cover and the controls on the left, the synced lines scrolling on
the right with the current line bright.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk

from encoregui.cover import CoverView
from encoregui.ui import icon_button, icon_image, set_icon
from encorelib.lyricview import lyric_row, lyric_rows

ART = 236
ART_EXPANDED = 330
EXPAND_MS = 220


def cover_path(state: dict) -> str:
    """The best cover in a state: the full-size one, else the lock-screen copy."""
    track = state.get("track") or {}
    return track.get("cover") or track.get("art") or ""


def meta_labels() -> tuple[Gtk.Label, Gtk.Label]:
    title = Gtk.Label(label="Nothing playing")
    title.add_css_class("title")
    title.set_ellipsize(3)
    title.set_max_width_chars(34)
    artist = Gtk.Label(label="")
    artist.add_css_class("artist")
    artist.set_ellipsize(3)
    artist.set_max_width_chars(40)
    return title, artist


class Transport(Gtk.Box):
    """Back 15 s, previous, play/pause, next, forward 15 s."""

    def __init__(self, win):
        super().__init__(spacing=12)
        self.set_halign(Gtk.Align.CENTER)
        self.play = icon_button(
            "media-playback-start-symbolic",
            lambda *_: win.ctl("play-pause"),
            big=True,
            tooltip="Play or pause",
        )
        self.play_icon = ""
        for widget in (
            icon_button(
                "media-seek-backward-symbolic", lambda *_: win.seek(-15), tooltip="Back 15 s"
            ),
            icon_button(
                "media-skip-backward-symbolic", lambda *_: win.ctl("previous"), tooltip="Previous"
            ),
            self.play,
            icon_button("media-skip-forward-symbolic", lambda *_: win.ctl("next"), tooltip="Next"),
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


class HomePage(Gtk.Box):
    def __init__(self, win):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.win = win
        self.set_valign(Gtk.Align.CENTER)
        self.set_halign(Gtk.Align.CENTER)
        self.expanded = 0.0  # 0..1 cover hover expansion
        self.expand_target = 0.0
        self.expand_timer = 0
        self.cover = CoverView(ART)
        self.cover.set_halign(Gtk.Align.CENTER)
        motion = Gtk.EventControllerMotion()
        motion.connect("enter", lambda *_: self._expand(1.0))
        motion.connect("leave", lambda *_: self._expand(0.0))
        self.cover.add_controller(motion)
        self.append(self.cover)
        self.title, self.artist = meta_labels()
        self.title.set_margin_top(8)
        self.append(self.title)
        self.append(self.artist)
        self.transport = Transport(win)
        self.transport.set_margin_top(8)
        self.append(self.transport)
        pill = lyrics_pill(win)
        pill.set_halign(Gtk.Align.CENTER)
        self.append(pill)

    def update(self, state: dict, _colors) -> None:
        track = state.get("track") or {}
        title = track.get("title") or "Nothing playing"
        artist = track.get("artist") or ""
        if self.title.get_label() != title:
            self.title.set_label(title)
        if self.artist.get_label() != artist:
            self.artist.set_label(artist)
        self.transport.update(state)
        self.cover.set_path(cover_path(state))

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
        self.win.backdrop.queue_draw()
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
        self.rows: list[Gtk.Label] = []
        self.key = ""
        self.current = -1
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
        left.append(self.title)
        left.append(self.artist)
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
        self.scroller = Gtk.ScrolledWindow()
        self.scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.EXTERNAL)
        self.scroller.set_hexpand(True)
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.box.set_margin_top(120)
        self.box.set_margin_bottom(220)
        self.scroller.set_child(self.box)
        card.append(self.scroller)

    def update(self, state: dict, _colors) -> None:
        track = state.get("track") or {}
        title = track.get("title") or "Nothing playing"
        artist = track.get("artist") or ""
        if self.title.get_label() != title:
            self.title.set_label(title)
        if self.artist.get_label() != artist:
            self.artist.set_label(artist)
        self.transport.update(state)
        self.cover.set_path(cover_path(state))
        self._sync_lines(state)

    def _sync_lines(self, state: dict) -> None:
        lyrics = state.get("lyrics") or {}
        lines = lyrics.get("lines") or []
        key = f"{(state.get('track') or {}).get('key', '')}:{len(lines)}"
        if key != self.key:
            self.key = key
            child = self.box.get_first_child()
            while child is not None:
                nxt = child.get_next_sibling()
                self.box.remove(child)
                child = nxt
            self.rows = []
            texts = lyric_rows(lines) or ["No synced lyrics for this track"]
            for text in texts:
                label = Gtk.Label(label=text, xalign=0)
                label.add_css_class("lyric")
                label.set_wrap(True)
                label.set_max_width_chars(36)
                self.box.append(label)
                self.rows.append(label)
            self.current = -1
        index = lyric_row(state)
        if index != self.current and self.rows:
            self.current = index
            for i, row in enumerate(self.rows):
                row.remove_css_class("current")
                row.remove_css_class("near")
                if i == index:
                    row.add_css_class("current")
                elif abs(i - index) == 1:
                    row.add_css_class("near")
            self.scroll_to_current(False)

    def scroll_to_current(self, instant: bool) -> None:
        if not self.rows or not (0 <= self.current < len(self.rows)):
            return
        ok, rect = self.rows[self.current].compute_bounds(self.box)
        if not ok:
            return
        adj = self.scroller.get_vadjustment()
        target = max(0.0, rect.get_y() - 120)
        if instant:
            adj.set_value(target)
            return
        start = adj.get_value()
        steps = 10
        counter = {"i": 0}

        def step():
            counter["i"] += 1
            t = counter["i"] / steps
            eased = 1 - (1 - t) ** 3
            adj.set_value(start + (target - start) * eased)
            return counter["i"] < steps

        GLib.timeout_add(16, step)
