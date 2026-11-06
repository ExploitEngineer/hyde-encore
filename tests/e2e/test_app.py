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

from encorelib.look import update_look
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
    from encorelib.look import read_look

    # through the CLI, as a keybind would: the look records both as on
    run_cli(lab, "toggle")
    run_cli(lab, "glow")
    for name in ("overlay", "glow"):
        lab.wait_until(lambda n=name: surface_alive(lab, n), f"{name} to start", 10)
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
    kept = read_look(lab.tmp / "state" / "hyde" / "encore.look")
    assert kept.get("desktop_lyrics_on") is False and kept.get("glow_on") is False


def run_cli(h: Harness, *args: str) -> None:
    import subprocess

    subprocess.run(
        [sys.executable, str(LIB / "encore.py"), *args],
        env=h.env,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )


def test_leaving_full_inside_the_hero_never_enters(lab):
    """Esc (or any page switch) during the 300 ms hero entry cancels it: the
    full page must not start its engine under Home later."""
    trace = lab.tmp / "trace.log"
    lab.env["ENCORE_TRACE"] = str(trace)
    _box, app = open_app(lab, lab.lab, "home")
    assert launch_app(lab, "full", "app-full.log").wait(10) == 0
    assert launch_app(lab, "home", "app-home.log").wait(10) == 0
    time.sleep(1.5)
    lines = trace.read_text().splitlines()
    # the last Home switch is the one that left Full screen (the first is the launch)
    home = max(i for i, ln in enumerate(lines) if "show_page home" in ln)
    entered = [i for i, ln in enumerate(lines) if "full.enter" in ln]
    if entered and entered[0] < home:
        pytest.skip("the hero finished before the test could leave")
    assert not entered, lines[home:]
    app.terminate()


def test_full_screen_enters_on_a_clear_background(lab):
    """With no cover to draw (Clear background, or a track without art) the hero
    entry still finishes and the lyrics engine starts."""
    trace = lab.tmp / "trace.log"
    lab.env["ENCORE_TRACE"] = str(trace)
    update_look(lab.run / "hyde" / "encore.look", stage_bg="clear")
    _box, app = open_app(lab, lab.lab, "full")
    time.sleep(1.5)
    lines = trace.read_text().splitlines()
    assert any("show_page full" in ln for ln in lines)
    assert any("full.enter" in ln for ln in lines), lines[-8:]
    assert (lab.run / "hyde" / "encore.stage").exists()
    app.terminate()


def move_lab_window(workspace: str) -> None:
    """Move the lab's Encore window, by address, without following it."""
    client = next(c for c in json.loads(hyprctl("clients", "-j")) if c["class"] == LAB_CLASS)
    hyprctl(
        "eval",
        f'hl.dispatch(hl.dsp.window.move({{workspace = "{workspace}", follow = false, '
        f'window = "address:{client["address"]}"}}))',
    )


def test_stage_flag_follows_the_window(lab):
    """The Stage hides the desktop overlay only while it is in sight: on a hidden
    workspace the flag goes, back on screen it returns."""
    flag = lab.run / "hyde" / "encore.stage"
    workspace = str(lab.lab.monitor()["activeWorkspace"]["id"])
    _box, app = open_app(lab, lab.lab, "stage")
    lab.wait_until(flag.exists, "the stage flag", 5)
    move_lab_window("special:encorelab")
    lab.wait_until(lambda: not flag.exists(), "the flag to go off screen", 5)
    move_lab_window(workspace)
    lab.wait_until(flag.exists, "the flag to come back", 5)
    close_window(lab)
    lab.wait_until(lambda: not flag.exists(), "the flag to go with the window", 10)
    app.wait(10)


def test_home_cover_is_back_to_size_after_full_then_stage(lab):
    """Home -> Full screen -> Stage -> Home: the cover the entry grew to 400 px is
    back at Home's size, not left big until the pointer hovers it."""
    trace = lab.tmp / "trace.log"
    lab.env["ENCORE_TRACE"] = str(trace)
    _box, app = open_app(lab, lab.lab, "home")
    assert launch_app(lab, "full", "app-full.log").wait(10) == 0
    lab.wait_until(lambda: "full.enter" in trace.read_text(), "the full screen entry", 10)
    assert launch_app(lab, "stage", "app-stage.log").wait(10) == 0
    assert launch_app(lab, "home", "app-home.log").wait(10) == 0
    lab.wait_until(lambda: "show_page home from stage" in trace.read_text(), "home", 10)
    sides = [ln.split()[-1] for ln in trace.read_text().splitlines() if "home cover" in ln]
    # Home's own size (256 px or a little more in this window), never the entry's 400
    assert 256 <= int(sides[-1]) < 300, sides
    app.terminate()


def resize_lab_window(width: int, height: int) -> None:
    client = next(c for c in json.loads(hyprctl("clients", "-j")) if c["class"] == LAB_CLASS)
    hyprctl(
        "eval",
        f"hl.dispatch(hl.dsp.window.resize({{x = {width}, y = {height}, exact = true, "
        f'window = "address:{client["address"]}"}}))',
    )


def lab_window_size() -> tuple[int, int]:
    client = next(c for c in json.loads(hyprctl("clients", "-j")) if c["class"] == LAB_CLASS)
    return tuple(client["size"])


def test_a_grown_window_shrinks_back(lab):
    """Home's cover and the Lyrics card grow with the window; their size must
    never become the window's minimum, or a tile change could not shrink it."""
    trace = lab.tmp / "trace.log"
    lab.env["ENCORE_TRACE"] = str(trace)
    _box, app = open_app(lab, lab.lab, "lyrics", size="1600 1000")
    time.sleep(1.5)  # the probes have sized the card for the big window
    resize_lab_window(900, 700)
    lab.wait_until(lambda: lab_window_size() == (900, 700), "the window to shrink", 5)
    time.sleep(1.0)

    def page_width() -> int:
        sizes = [ln.split()[-1] for ln in trace.read_text().splitlines() if "lyrics page" in ln]
        return int(sizes[-1].split("x")[0])

    # GTK lays the page out at the window's new width, not at a raised minimum
    assert page_width() <= 900
    app.terminate()
