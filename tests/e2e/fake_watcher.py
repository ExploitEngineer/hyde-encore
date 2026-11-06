#!/usr/bin/env python3
"""A minimal org.kde.StatusNotifierWatcher for the private test bus.

Records every RegisterStatusNotifierItem call so tests can ask, through its
RegisteredStatusNotifierItems property, whether Encore put an item in the
tray. Nothing is drawn.
"""

from __future__ import annotations

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

NAME = "org.kde.StatusNotifierWatcher"
PATH = "/StatusNotifierWatcher"
XML = """
<node>
  <interface name="org.kde.StatusNotifierWatcher">
    <method name="RegisterStatusNotifierItem"><arg type="s" direction="in"/></method>
    <method name="RegisterStatusNotifierHost"><arg type="s" direction="in"/></method>
    <property name="RegisteredStatusNotifierItems" type="as" access="read"/>
    <property name="IsStatusNotifierHostRegistered" type="b" access="read"/>
    <property name="ProtocolVersion" type="i" access="read"/>
    <signal name="StatusNotifierItemRegistered"><arg type="s"/></signal>
    <signal name="StatusNotifierItemUnregistered"><arg type="s"/></signal>
    <signal name="StatusNotifierHostRegistered"/>
  </interface>
</node>
"""


class Watcher:
    def __init__(self, conn: Gio.DBusConnection):
        self.conn = conn
        self.items: list[str] = []

    def call(self, _c, sender, _p, _i, method, params, invocation) -> None:
        if method == "RegisterStatusNotifierItem":
            (service,) = params.unpack()
            # a bare path means "this sender at that path", as hosts resolve it
            item = f"{sender}{service}" if service.startswith("/") else service
            if item not in self.items:
                self.items.append(item)
            self.conn.emit_signal(
                None, PATH, NAME, "StatusNotifierItemRegistered", GLib.Variant("(s)", (item,))
            )
        invocation.return_value(None)

    def get(self, _c, _s, _p, _i, prop) -> GLib.Variant:
        return {
            "RegisteredStatusNotifierItems": GLib.Variant("as", self.items),
            "IsStatusNotifierHostRegistered": GLib.Variant("b", True),
            "ProtocolVersion": GLib.Variant("i", 0),
        }[prop]


def main() -> None:
    node = Gio.DBusNodeInfo.new_for_xml(XML)
    conn = Gio.bus_get_sync(Gio.BusType.SESSION)
    watcher = Watcher(conn)
    conn.register_object(PATH, node.interfaces[0], watcher.call, watcher.get, None)
    Gio.bus_own_name_on_connection(conn, NAME, Gio.BusNameOwnerFlags.NONE, None, None)
    GLib.MainLoop().run()


if __name__ == "__main__":
    main()
