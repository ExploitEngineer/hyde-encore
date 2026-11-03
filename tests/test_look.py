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
    assert effective(cfg, {}) == ("line", "JetBrainsMono Nerd Font", 30, "", True, True)
