from encorelib.look import read_look
from encorelib.profiles import PROFILES, apply_profile


def test_profiles_exist():
    assert set(PROFILES) == {"working", "show"}
    assert PROFILES["working"]["glow"] is False
    assert PROFILES["show"]["glow"] is True


def test_apply_profile_writes_look_and_reports_glow(tmp_path):
    p = tmp_path / "encore.look"
    glow = apply_profile(p, "show")
    assert glow is True
    look = read_look(p)
    assert look["style"] == PROFILES["show"]["look"]["style"]
    assert look["motion"] is True
    glow = apply_profile(p, "working")
    assert glow is False
    assert read_look(p)["style"] == "line"


def test_apply_unknown_profile(tmp_path):
    assert apply_profile(tmp_path / "x", "party") is None


def test_show_action_toggles_by_workspace_name():
    from encorelib.profiles import SHOW_WORKSPACE, show_action

    assert show_action("3") == "enter"
    assert show_action(SHOW_WORKSPACE) == "leave"
    assert show_action("") == "enter"
