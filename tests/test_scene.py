"""Scene draws real render nodes (needs PyGObject with the GTK 4 typelibs)."""

import pytest

gi = pytest.importorskip("gi")


@pytest.fixture
def gtk():
    try:
        gi.require_version("Gtk", "4.0")
        gi.require_version("Gsk", "4.0")
        from gi.repository import Gsk, Gtk
    except (ImportError, ValueError) as e:
        pytest.skip(f"GTK typelibs unavailable: {e}")
    return Gtk, Gsk


def bounds(node):
    b = node.get_bounds()
    return (
        round(b.get_x(), 3),
        round(b.get_y(), 3),
        round(b.get_width(), 3),
        round(b.get_height(), 3),
    )


def test_rounded_clip_keeps_its_rect(gtk):
    Gtk, Gsk = gtk
    from encoregui.scene import Scene

    snapshot = Gtk.Snapshot()
    sc = Scene(snapshot)
    with sc.rounded_clip(10, 20, 100, 50, 8):
        sc.rect(0, 0, 400, 400, (1, 0, 0))
    node = snapshot.to_node()
    assert node.get_node_type() == Gsk.RenderNodeType.ROUNDED_CLIP_NODE
    assert bounds(node) == (10, 20, 100, 50)


def test_shadow_surrounds_its_box(gtk):
    Gtk, Gsk = gtk
    from encoregui.scene import Scene

    snapshot = Gtk.Snapshot()
    Scene(snapshot).shadow(100, 100, 50, 50, 6, 0.5, dy=0, blur=0)
    node = snapshot.to_node()
    assert node.get_node_type() == Gsk.RenderNodeType.OUTSET_SHADOW_NODE
    assert bounds(node) == (100, 100, 50, 50)
