from encorelib.look import read_look
from encorelib.profiles import PROFILES, apply_profile


def test_profiles_exist():
    assert set(PROFILES) == {"working"}
    assert PROFILES["working"]["glow"] is False


def test_apply_profile_writes_look_and_reports_glow(tmp_path):
    p = tmp_path / "encore.look"
    glow = apply_profile(p, "working")
    assert glow is False
    look = read_look(p)
    assert look["style"] == "line"
    assert look["motion"] is False


def test_apply_profile_persists(tmp_path):
    p, keep = tmp_path / "encore.look", tmp_path / "keep.look"
    apply_profile(p, "working", persist=keep)
    assert read_look(keep) == read_look(p)


def test_apply_unknown_profile(tmp_path):
    assert apply_profile(tmp_path / "x", "party") is None
