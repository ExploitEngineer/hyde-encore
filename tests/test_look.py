import json
from pathlib import Path

from encorelib.config import EncoreConfig
from encorelib.look import (
    effective,
    effective_players,
    read_look,
    restore_look,
    state_look_path,
    update_look,
)


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


def test_new_keys_validate(tmp_path):
    p = tmp_path / "encore.look"
    good = {
        "stage_bg": "clear",
        "hd_covers": False,
        "autostart": True,
        "desktop_lyrics_on": True,
        "glow_on": False,
        "players": ["spotify", "brave"],
        "lock_previous": "Anurati",
    }
    update_look(p, **good)
    assert read_look(p) == good


def test_new_keys_reject_bad_values(tmp_path):
    p = tmp_path / "encore.look"
    update_look(
        p,
        stage_bg="blur",
        hd_covers="yes",
        autostart=1,
        players=["a" * 65],
        lock_previous="",
    )
    assert read_look(p) == {}
    update_look(p, players=[f"p{i}" for i in range(17)])
    assert read_look(p) == {}
    update_look(p, players=[])  # empty means follow every player
    assert read_look(p) == {"players": []}


def test_update_mirrors_to_persist(tmp_path):
    runtime, keep = tmp_path / "run" / "encore.look", tmp_path / "state" / "encore.look"
    update_look(runtime, persist=keep, style="stack")
    update_look(runtime, persist=keep, size=40)
    assert read_look(keep) == read_look(runtime) == {"style": "stack", "size": 40}


def test_update_without_persist_leaves_it(tmp_path):
    runtime, keep = tmp_path / "run" / "encore.look", tmp_path / "state" / "encore.look"
    update_look(runtime, style="stack")
    assert not keep.exists()


def test_restore_only_when_runtime_missing(tmp_path):
    runtime, keep = tmp_path / "run" / "encore.look", tmp_path / "state" / "encore.look"
    assert restore_look(runtime, keep) is False  # nothing kept yet
    keep.parent.mkdir()
    keep.write_text(json.dumps({"style": "visual", "junk": 1}))
    assert restore_look(runtime, keep) is True
    assert read_look(runtime) == {"style": "visual"}
    update_look(runtime, style="line")
    assert restore_look(runtime, keep) is False
    assert read_look(runtime) == {"style": "line"}


def test_state_look_path():
    assert state_look_path({"XDG_STATE_HOME": "/s", "HOME": "/h"}) == Path("/s/hyde/encore.look")
    assert state_look_path({"HOME": "/h"}) == Path("/h/.local/state/hyde/encore.look")


def test_effective_players():
    cfg = EncoreConfig(players=("spotify",))
    assert effective_players(cfg, {}) == ("spotify",)
    assert effective_players(cfg, {"players": ["brave"]}) == ("brave",)
    assert effective_players(cfg, {"players": []}) == ()  # the app's "follow every player"


def test_effective_autostart_lets_the_app_override_config():
    from encorelib.look import effective_autostart

    assert effective_autostart(EncoreConfig(enable=True), {}) is True
    assert effective_autostart(EncoreConfig(enable=True), {"autostart": False}) is False
    assert effective_autostart(EncoreConfig(enable=False), {"autostart": True}) is True
