#!/usr/bin/env python3
"""A scriptable fake MPRIS player for end-to-end testing encore.

Run it, then drive it like any player:
    python3 tests/e2e/fake_mpris.py [--art /path/cover.png] [--name encoretest] &
    playerctl -p encoretest play|pause|next|position 60

Track 1 is "Never Gonna Give You Up", track 2 "Blinding Lights".
Not shipped to HyDE; development aid only.
"""

import argparse
import time

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

XML = """
<node>
  <interface name="org.mpris.MediaPlayer2">
    <method name="Raise"/><method name="Quit"/>
    <property name="Identity" type="s" access="read"/>
    <property name="CanQuit" type="b" access="read"/>
    <property name="CanRaise" type="b" access="read"/>
    <property name="HasTrackList" type="b" access="read"/>
    <property name="SupportedUriSchemes" type="as" access="read"/>
    <property name="SupportedMimeTypes" type="as" access="read"/>
  </interface>
  <interface name="org.mpris.MediaPlayer2.Player">
    <method name="Play"/><method name="Pause"/><method name="PlayPause"/>
    <method name="Stop"/><method name="Next"/><method name="Previous"/>
    <method name="Seek"><arg direction="in" name="Offset" type="x"/></method>
    <method name="SetPosition">
      <arg direction="in" name="TrackId" type="o"/><arg direction="in" name="Position" type="x"/>
    </method>
    <signal name="Seeked"><arg name="Position" type="x"/></signal>
    <property name="PlaybackStatus" type="s" access="read"/>
    <property name="Metadata" type="a{sv}" access="read"/>
    <property name="Position" type="x" access="read"/>
    <property name="Rate" type="d" access="read"/>
    <property name="Volume" type="d" access="read"/>
    <property name="CanGoNext" type="b" access="read"/>
    <property name="CanGoPrevious" type="b" access="read"/>
    <property name="CanPlay" type="b" access="read"/>
    <property name="CanPause" type="b" access="read"/>
    <property name="CanSeek" type="b" access="read"/>
    <property name="CanControl" type="b" access="read"/>
  </interface>
</node>
"""

TRACKS = [
    ("Never Gonna Give You Up", "Rick Astley", "Whenever You Need Somebody", 213),
    ("Blinding Lights", "The Weeknd", "After Hours", 200),
]
PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"


class FakePlayer:
    def __init__(self, conn: Gio.DBusConnection, art: str):
        self.conn = conn
        self.art = art
        self.index = 0
        self.status = "Paused"
        self.base = 0.0
        self.since = time.monotonic()

    def position(self) -> float:
        if self.status == "Playing":
            return self.base + time.monotonic() - self.since
        return self.base

    def set_position(self, seconds: float) -> None:
        self.base, self.since = max(0.0, seconds), time.monotonic()

    def metadata(self) -> GLib.Variant:
        title, artist, album, length = TRACKS[self.index]
        md = {
            "mpris:trackid": GLib.Variant("o", f"/org/mpris/MediaPlayer2/Track/{self.index + 1}"),
            "mpris:length": GLib.Variant("x", length * 1_000_000),
            "xesam:title": GLib.Variant("s", title),
            "xesam:artist": GLib.Variant("as", [artist]),
            "xesam:album": GLib.Variant("s", album),
        }
        if self.art:
            md["mpris:artUrl"] = GLib.Variant("s", f"file://{self.art}")
        return GLib.Variant("a{sv}", md)

    def changed(self, **props: GLib.Variant) -> None:
        self.conn.emit_signal(
            None,
            "/org/mpris/MediaPlayer2",
            "org.freedesktop.DBus.Properties",
            "PropertiesChanged",
            GLib.Variant("(sa{sv}as)", (PLAYER_IFACE, props, [])),
        )

    def seeked(self) -> None:
        self.conn.emit_signal(
            None,
            "/org/mpris/MediaPlayer2",
            PLAYER_IFACE,
            "Seeked",
            GLib.Variant("(x)", (int(self.position() * 1e6),)),
        )

    def call(self, _c, _s, _p, _i, method, params, invocation) -> None:
        if method in ("Play", "Pause", "PlayPause", "Stop"):
            pos = self.position()
            if method == "PlayPause":
                self.status = "Paused" if self.status == "Playing" else "Playing"
            else:
                self.status = {"Play": "Playing", "Pause": "Paused", "Stop": "Stopped"}[method]
            self.set_position(0.0 if method == "Stop" else pos)
            self.changed(PlaybackStatus=GLib.Variant("s", self.status))
        elif method in ("Next", "Previous"):
            self.index = (self.index + (1 if method == "Next" else -1)) % len(TRACKS)
            self.set_position(0.0)
            self.changed(Metadata=self.metadata())
        elif method == "Seek":
            self.set_position(self.position() + params.unpack()[0] / 1e6)
            self.seeked()
        elif method == "SetPosition":
            self.set_position(params.unpack()[1] / 1e6)
            self.seeked()
        invocation.return_value(None)

    def get(self, _c, _s, _p, _i, prop) -> GLib.Variant:
        values = {
            "Identity": GLib.Variant("s", "encore test player"),
            "CanQuit": GLib.Variant("b", False),
            "CanRaise": GLib.Variant("b", False),
            "HasTrackList": GLib.Variant("b", False),
            "SupportedUriSchemes": GLib.Variant("as", []),
            "SupportedMimeTypes": GLib.Variant("as", []),
            "PlaybackStatus": GLib.Variant("s", self.status),
            "Metadata": self.metadata(),
            "Position": GLib.Variant("x", int(self.position() * 1e6)),
            "Rate": GLib.Variant("d", 1.0),
            "Volume": GLib.Variant("d", 1.0),
        }
        return values.get(prop, GLib.Variant("b", True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--art", default="", help="absolute path to a cover image")
    parser.add_argument("--name", default="encoretest", help="MPRIS bus name suffix")
    args = parser.parse_args()
    node = Gio.DBusNodeInfo.new_for_xml(XML)
    conn = Gio.bus_get_sync(Gio.BusType.SESSION)
    player = FakePlayer(conn, args.art)
    for iface in node.interfaces:
        conn.register_object("/org/mpris/MediaPlayer2", iface, player.call, player.get, None)
    Gio.bus_own_name_on_connection(
        conn, f"org.mpris.MediaPlayer2.{args.name}", Gio.BusNameOwnerFlags.NONE, None, None
    )
    GLib.MainLoop().run()


if __name__ == "__main__":
    main()
