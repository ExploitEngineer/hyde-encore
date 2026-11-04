import json

from encorelib.config import EncoreConfig
from encorelib.look import effective, read_look, update_look


def test_read_missing_and_garbage(tmp_path):
    p = tmp_path / "encore.look"
    assert read_look(p) == {}
    p.write_text("{not json")
    assert read_look(p) == {}
    p.write_text(json.dumps({"style": "stack", "size": "huge", "font": 3, "junk": 1}))
    assert read_look(p) == {"style": "stack"}


def test_update_look_merges_and_validates(tmp_path):
    p = tmp_path / "encore.look"
    update_look(p, style="constellation")
    update_look(p, size=40, color="#AABBCC")
    assert read_look(p) == {"style": "constellation", "size": 40, "color": "#AABBCC"}
    update_look(p, style=None)  # None removes a key
    assert read_look(p) == {"size": 40, "color": "#AABBCC"}


def test_update_rejects_invalid(tmp_path):
    p = tmp_path / "encore.look"
    update_look(p, style="wave", size=900, color="red", font="", next_line="maybe")
    assert read_look(p) == {}


def test_effective_overrides_config(tmp_path):
    cfg = EncoreConfig(
        overlay_style="line", overlay_font="JetBrainsMono Nerd Font", overlay_size=30
    )
    look = {
        "style": "stack",
        "font": "Futura",
        "size": 44,
        "color": "#FF00AA",
        "next_line": False,
        "motion": False,
    }
    assert effective(cfg, look) == ("stack", "Futura", 44, "#FF00AA", False, False)
    assert effective(cfg, {}) == (
        "line",
        "JetBrainsMono Nerd Font",
        30,
        "",
        True,
        True,
    )


def test_color_trio_and_glow_keys(tmp_path):
    p = tmp_path / "encore.look"
    update_look(
        p,
        lyric_color="#F2A7C3",
        highlight_color="#C2185B",
        secondary_color="#A87C9A",
        glow_colors=2,
        glow_animation="breathe",
        glow_thickness=160,
        glow_intensity=80,
        glow_override=True,
        glow_primary="#3355FF",
        glow_secondary="#AA00FF",
    )
    look = read_look(p)
    assert look["highlight_color"] == "#C2185B"
    assert look["glow_colors"] == 2
    assert look["glow_animation"] == "breathe"
    assert look["glow_thickness"] == 160
    assert look["glow_intensity"] == 80
    assert look["glow_override"] is True
    assert look["glow_secondary"] == "#AA00FF"


def test_glow_keys_rejected_out_of_range(tmp_path):
    p = tmp_path / "encore.look"
    update_look(
        p,
        glow_colors=3,
        glow_animation="disco",
        glow_thickness=5,
        glow_intensity=500,
        lyric_color="pink",
    )
    assert read_look(p) == {}


def test_glow_monitor_is_a_look_key(tmp_path):
    from encorelib.look import read_look, update_look

    path = tmp_path / "encore.look"
    update_look(path, glow_monitor="HDMI-A-1")
    assert read_look(path)["glow_monitor"] == "HDMI-A-1"
    update_look(path, glow_monitor="")  # empty is not a connector
    assert read_look(path)["glow_monitor"] == "HDMI-A-1"
    update_look(path, glow_monitor=None)
    assert "glow_monitor" not in read_look(path)
