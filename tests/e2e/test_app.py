"""The Encore window on the hidden lab monitor: launching, closing, the tray, Quit.

Opt in with `python3 -m pytest -m lab tests/e2e/test_app.py`: these open real
windows (on the hidden monitor only) and need a running Hyprland.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import gi
import pytest

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib
from harness import LIB, Harness, write_png
from stage import LAB, LAB_CLASS, Lab, hyprctl, launch_app, open_app

from encorelib.single import pid_alive, read_pid

pytestmark = [pytest.mark.e2e, pytest.mark.lab]
WATCHER = Path(__file__).resolve().parent / "fake_watcher.py"


@pytest.fixture
def lab(harness: Harness):
    """A harness with the lab monitor, a tray watcher and a playing fake player."""
    with Lab() as monitor:
        harness.env.update(ENCORE_OVERLAY_MONITOR=LAB, ENCORE_GLOW_MONITOR=LAB, GTK_A11Y="none")
        harness._spawn([sys.executable, str(WATCHER)], "watcher.log")
        harness.start_player(art=str(write_png(harness.tmp / "cover.png")))
        harness.start_daemon()
        harness.ctl("encoretest", "play")
        harness.wait(lambda s: s["status"] == "playing", 15)
        harness.lab = monitor
        yield harness


def bus(h: Harness) -> Gio.DBusConnection:
    return Gio.DBusConnection.new_for_address_sync(
        h.env["DBUS_SESSION_BUS_ADDRESS"],
        Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT
        | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
        None,
        None,
    )


def tray_items(h: Harness) -> list[str]:
    reply = bus(h).call_sync(
        "org.kde.StatusNotifierWatcher",
        "/StatusNotifierWatcher",
        "org.freedesktop.DBus.Properties",
        "Get",
        GLib.Variant("(ss)", ("org.kde.StatusNotifierWatcher", "RegisteredStatusNotifierItems")),
        None,
        Gio.DBusCallFlags.NONE,
        3000,
        None,
    )
    return list(reply.unpack()[0])


def menu_layout(h: Harness) -> dict[int, dict]:
    """Item id -> properties of Encore's tray menu, straight from its D-Bus menu."""
    reply = bus(h).call_sync(
        LAB_CLASS,
        "/MenuBar",
        "com.canonical.dbusmenu",
        "GetLayout",
        GLib.Variant("(iias)", (0, -1, [])),
        None,
        Gio.DBusCallFlags.NONE,
        3000,
        None,
    )
    _revision, (_root, _props, children) = reply.unpack()
    return {child[0]: child[1] for child in children}


def click_menu(h: Harness, item_id: int) -> None:
    bus(h).call_sync(
        LAB_CLASS,
        "/MenuBar",
        "com.canonical.dbusmenu",
        "Event",
        GLib.Variant("(isvu)", (item_id, "clicked", GLib.Variant("s", ""), 0)),
        None,
        Gio.DBusCallFlags.NONE,
        3000,
        None,
    )


def windows() -> int:
    clients = json.loads(hyprctl("clients", "-j") or "[]")
    return len([c for c in clients if c.get("class") == LAB_CLASS])


def close_window(h: Harness) -> None:
    """Ask the window to close, through the app's close action (the same
    close-request path as the title bar's button)."""
    bus(h).call_sync(
        LAB_CLASS,
        "/" + LAB_CLASS.replace(".", "/"),
        "org.gtk.Actions",
        "Activate",
        GLib.Variant("(sava{sv})", ("close", [], {})),
        None,
        Gio.DBusCallFlags.NONE,
        3000,
        None,
    )


def start_surface(h: Harness, name: str) -> None:
    h._spawn(
        ["bash", str(LIB / "encore.sh"), name, *(["--run"] if name == "glow" else [])],
        f"{name}.log",
    )
    pidfile = h.run / "hyde" / f"encore-{name}.pid"
    h.wait_until(
        lambda: (pid := read_pid(pidfile)) is not None and pid_alive(pid), f"{name} to start"
    )


def surface_alive(h: Harness, name: str) -> bool:
    pid = read_pid(h.run / "hyde" / f"encore-{name}.pid")
    return pid is not None and pid_alive(pid)


def test_second_launch_presents_one_window(lab):
    _box, app = open_app(lab, lab.lab, "home")
    second = launch_app(lab, "home", "app-second.log")
    assert second.wait(10) == 0
    assert windows() == 1
    assert app.poll() is None
    app.terminate()


def test_close_with_nothing_on_quits(lab):
    _box, app = open_app(lab, lab.lab, "home")
    close_window(lab)
    assert app.wait(10) == 0
    assert windows() == 0
    assert tray_items(lab) == []


def test_close_with_glow_hides_and_registers_tray(lab):
    start_surface(lab, "glow")
    _box, app = open_app(lab, lab.lab, "home")
    close_window(lab)
    lab.wait_until(lambda: windows() == 0, "the window to hide")
    time.sleep(1.5)
    assert app.poll() is None  # still running, in the tray
    assert len(tray_items(lab)) == 1
    assert menu_layout(lab)[5]["toggle-state"] == 1  # Glow shows as on
    assert menu_layout(lab)[4]["toggle-state"] == 0
    click_menu(lab, 1)  # Open Encore
    lab.wait_until(lambda: windows() == 1, "the window to come back")
    app.terminate()


def test_app_reflects_running_surfaces(lab):
    start_surface(lab, "overlay")
    start_surface(lab, "glow")
    _box, app = open_app(lab, lab.lab, "home")
    close_window(lab)
    lab.wait_until(lambda: windows() == 0, "the window to hide")
    lab.wait_until(lambda: len(tray_items(lab)) == 1, "the tray item")
    layout = menu_layout(lab)
    assert layout[4]["toggle-state"] == 1 and layout[5]["toggle-state"] == 1
    assert layout[2]["label"] == "Pause"
    click_menu(lab, 5)  # Glow off from the tray
    lab.wait_until(lambda: not surface_alive(lab, "glow"), "the glow to stop", 10)
    lab.wait_until(lambda: menu_layout(lab)[5]["toggle-state"] == 0, "the menu to follow", 10)
    assert surface_alive(lab, "overlay")
    app.terminate()


def test_quit_stops_overlay_and_glow(lab):
    start_surface(lab, "overlay")
    start_surface(lab, "glow")
    _box, app = open_app(lab, lab.lab, "full")
    assert (lab.run / "hyde" / "encore.stage").exists()
    close_window(lab)
    lab.wait_until(lambda: len(tray_items(lab)) == 1, "the tray item")
    click_menu(lab, 7)  # Quit
    assert app.wait(10) == 0
    lab.wait_until(lambda: not surface_alive(lab, "overlay"), "the overlay to stop", 10)
    lab.wait_until(lambda: not surface_alive(lab, "glow"), "the glow to stop", 10)
    assert not (lab.run / "hyde" / "encore.stage").exists()
    assert lab.state() is not None  # the engine keeps running for the lock screen
