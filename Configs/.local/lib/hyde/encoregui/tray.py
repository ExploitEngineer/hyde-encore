"""Encore in the tray while its window is closed: a StatusNotifierItem.

Exports org.kde.StatusNotifierItem at /StatusNotifierItem and its menu as
com.canonical.dbusmenu at /MenuBar on the session bus (plain Gio, no extra
library), and registers with org.kde.StatusNotifierWatcher whenever one is
there, so waybar's tray module shows the Encore icon with Open, Play/Pause,
Next, Desktop lyrics, Glow and Quit. The menu's contents come from
encorelib.dbusmenu.
"""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

from encorelib.dbusmenu import ACTIONS, layout

WATCHER = "org.kde.StatusNotifierWatcher"
WATCHER_PATH = "/StatusNotifierWatcher"
ITEM_PATH = "/StatusNotifierItem"
MENU_PATH = "/MenuBar"
ICON = "org.hyde.encore"

ITEM_XML = """
<node>
  <interface name="org.kde.StatusNotifierItem">
    <property name="Category" type="s" access="read"/>
    <property name="Id" type="s" access="read"/>
    <property name="Title" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="IconName" type="s" access="read"/>
    <property name="IconThemePath" type="s" access="read"/>
    <property name="Menu" type="o" access="read"/>
    <property name="ItemIsMenu" type="b" access="read"/>
    <method name="Activate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
    <method name="SecondaryActivate">
      <arg type="i" direction="in"/><arg type="i" direction="in"/>
    </method>
    <method name="ContextMenu"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
    <method name="Scroll"><arg type="i" direction="in"/><arg type="s" direction="in"/></method>
    <signal name="NewIcon"/>
    <signal name="NewTitle"/>
    <signal name="NewStatus"><arg type="s"/></signal>
  </interface>
</node>
"""

MENU_XML = """
<node>
  <interface name="com.canonical.dbusmenu">
    <property name="Version" type="u" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="TextDirection" type="s" access="read"/>
    <property name="IconThemePath" type="as" access="read"/>
    <method name="GetLayout">
      <arg type="i" direction="in"/><arg type="i" direction="in"/><arg type="as" direction="in"/>
      <arg type="u" direction="out"/><arg type="(ia{sv}av)" direction="out"/>
    </method>
    <method name="GetGroupProperties">
      <arg type="ai" direction="in"/><arg type="as" direction="in"/>
      <arg type="a(ia{sv})" direction="out"/>
    </method>
    <method name="GetProperty">
      <arg type="i" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="out"/>
    </method>
    <method name="Event">
      <arg type="i" direction="in"/><arg type="s" direction="in"/>
      <arg type="v" direction="in"/><arg type="u" direction="in"/>
    </method>
    <method name="EventGroup">
      <arg type="a(isvu)" direction="in"/><arg type="ai" direction="out"/>
    </method>
    <method name="AboutToShow"><arg type="i" direction="in"/><arg type="b" direction="out"/></method>
    <method name="AboutToShowGroup">
      <arg type="ai" direction="in"/><arg type="ai" direction="out"/><arg type="ai" direction="out"/>
    </method>
    <signal name="LayoutUpdated"><arg type="u"/><arg type="i"/></signal>
    <signal name="ItemsPropertiesUpdated">
      <arg type="a(ia{sv})"/><arg type="a(ias)"/>
    </signal>
  </interface>
</node>
"""


def _sv(props: dict) -> dict:
    """Menu item properties as a{sv} values."""
    out = {}
    for key, value in props.items():
        if isinstance(value, bool):
            out[key] = GLib.Variant("b", value)
        elif isinstance(value, int):
            out[key] = GLib.Variant("i", value)
        else:
            out[key] = GLib.Variant("s", str(value))
    return out


def _item_variant(item: tuple) -> GLib.Variant:
    item_id, props, children = item
    kids = [GLib.Variant("v", _item_variant(child)) for child in children]
    return GLib.Variant("(ia{sv}av)", (item_id, _sv(props), kids))


class Tray:
    def __init__(self):
        self.conn: Gio.DBusConnection | None = None
        self.registrations: list[int] = []
        self.watch_id = 0
        self.revision = 1
        self.state = (False, False, False)  # desktop_on, glow_on, playing
        self.on_activate: Callable[[], None] = lambda: None
        self.on_action: Callable[[str], None] = lambda _a: None
        self.active = False

    # life cycle ---------------------------------------------------------------

    def start(self, on_activate: Callable[[], None], on_action: Callable[[str], None]) -> bool:
        """Put Encore in the tray; False when no StatusNotifier watcher is on the bus."""
        self.on_activate, self.on_action = on_activate, on_action
        self.active = True
        if self.conn is None:
            self.conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            item = Gio.DBusNodeInfo.new_for_xml(ITEM_XML).interfaces[0]
            menu = Gio.DBusNodeInfo.new_for_xml(MENU_XML).interfaces[0]
            self.registrations = [
                self.conn.register_object(ITEM_PATH, item, self._item_call, self._item_get, None),
                self.conn.register_object(MENU_PATH, menu, self._menu_call, self._menu_get, None),
            ]
        if not self.watch_id:
            # the watcher may start after Encore (waybar restarts): register whenever it appears
            self.watch_id = Gio.bus_watch_name_on_connection(
                self.conn, WATCHER, Gio.BusNameWatcherFlags.NONE, self._register, None
            )
        return self._watcher_present()

    def stop(self) -> None:
        """Leave the tray (the window is back); the objects stay exported, unused."""
        self.active = False
        if self.watch_id:
            Gio.bus_unwatch_name(self.watch_id)
            self.watch_id = 0
        if self.conn is not None:
            self._emit_item("NewStatus", GLib.Variant("(s)", ("Passive",)))

    def update(self, desktop_on: bool, glow_on: bool, playing: bool) -> None:
        state = (desktop_on, glow_on, playing)
        if state == self.state:
            return
        self.state = state
        self.revision += 1
        if self.conn is not None:
            self.conn.emit_signal(
                None,
                MENU_PATH,
                "com.canonical.dbusmenu",
                "LayoutUpdated",
                GLib.Variant("(ui)", (self.revision, 0)),
            )

    # registration -------------------------------------------------------------

    def _watcher_present(self) -> bool:
        try:
            reply = self.conn.call_sync(
                "org.freedesktop.DBus",
                "/org/freedesktop/DBus",
                "org.freedesktop.DBus",
                "NameHasOwner",
                GLib.Variant("(s)", (WATCHER,)),
                GLib.VariantType("(b)"),
                Gio.DBusCallFlags.NONE,
                1000,
                None,
            )
        except GLib.Error:
            return False
        return bool(reply.unpack()[0])

    def _register(self, conn, _name, _owner) -> None:
        if not self.active:
            return
        conn.call(
            WATCHER,
            WATCHER_PATH,
            WATCHER,
            "RegisterStatusNotifierItem",
            GLib.Variant("(s)", (conn.get_unique_name(),)),
            None,
            Gio.DBusCallFlags.NONE,
            2000,
            None,
            lambda c, result: self._registered(c, result),
        )
        self._emit_item("NewStatus", GLib.Variant("(s)", ("Active",)))

    @staticmethod
    def _registered(conn, result) -> None:
        try:
            conn.call_finish(result)
        except GLib.Error:
            pass  # a watcher that refuses us: nothing to show, nothing to break

    def _emit_item(self, signal: str, params: GLib.Variant | None) -> None:
        self.conn.emit_signal(None, ITEM_PATH, "org.kde.StatusNotifierItem", signal, params)

    # org.kde.StatusNotifierItem -----------------------------------------------

    def _item_get(self, _c, _s, _p, _i, prop) -> GLib.Variant:
        values = {
            "Category": GLib.Variant("s", "ApplicationStatus"),
            "Id": GLib.Variant("s", "org.hyde.encore"),
            "Title": GLib.Variant("s", "Encore"),
            "Status": GLib.Variant("s", "Active" if self.active else "Passive"),
            "IconName": GLib.Variant("s", ICON),
            "IconThemePath": GLib.Variant("s", ""),
            "Menu": GLib.Variant("o", MENU_PATH),
            "ItemIsMenu": GLib.Variant("b", False),
        }
        return values[prop]

    def _item_call(self, _c, _s, _p, _i, method, _params, invocation) -> None:
        if method in ("Activate", "SecondaryActivate"):
            self.on_activate()
        invocation.return_value(None)

    # com.canonical.dbusmenu ---------------------------------------------------

    def _menu_get(self, _c, _s, _p, _i, prop) -> GLib.Variant:
        values = {
            "Version": GLib.Variant("u", 3),
            "Status": GLib.Variant("s", "normal"),
            "TextDirection": GLib.Variant("s", "ltr"),
            "IconThemePath": GLib.Variant("as", []),
        }
        return values[prop]

    def _menu_call(self, _c, _s, _p, _i, method, params, invocation) -> None:
        tree = layout(*self.state)
        if method == "GetLayout":
            parent = params.unpack()[0]
            node = tree if parent == 0 else next((i for i in tree[2] if i[0] == parent), None)
            if node is None:
                invocation.return_dbus_error("com.canonical.dbusmenu.Error", "no such item")
                return
            invocation.return_value(
                GLib.Variant.new_tuple(GLib.Variant("u", self.revision), _item_variant(node))
            )
        elif method == "GetGroupProperties":
            wanted = set(params.unpack()[0])
            rows = [(i, _sv(p)) for i, p, _k in tree[2] if not wanted or i in wanted]
            invocation.return_value(GLib.Variant("(a(ia{sv}))", (rows,)))
        elif method == "GetProperty":
            item_id, name = params.unpack()
            props = next((p for i, p, _k in tree[2] if i == item_id), {})
            value = _sv(props).get(name, GLib.Variant("s", ""))
            invocation.return_value(GLib.Variant.new_tuple(GLib.Variant("v", value)))
        elif method == "Event":
            item_id, event = params.unpack()[:2]
            if event == "clicked" and item_id in ACTIONS:
                self.on_action(ACTIONS[item_id])
            invocation.return_value(None)
        elif method == "EventGroup":
            for item_id, event, _data, _ts in params.unpack()[0]:
                if event == "clicked" and item_id in ACTIONS:
                    self.on_action(ACTIONS[item_id])
            invocation.return_value(GLib.Variant("(ai)", ([],)))
        elif method == "AboutToShow":
            invocation.return_value(GLib.Variant("(b)", (False,)))
        elif method == "AboutToShowGroup":
            invocation.return_value(GLib.Variant("(aiai)", ([], [])))
        else:
            invocation.return_dbus_error("org.freedesktop.DBus.Error.UnknownMethod", method)
