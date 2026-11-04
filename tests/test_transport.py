from encorelib.transport import fmt_time, key_action, seek_to, step_volume


def test_fmt_time():
    assert [fmt_time(s) for s in (0, 7.9, 188, 3723)] == ["0:00", "0:07", "3:08", "1:02:03"]
    assert fmt_time(-3) == "0:00"


def test_seek_clamps_to_the_track():
    assert seek_to(5, -15, 200) == 0
    assert seek_to(195, 15, 200) == 199
    assert seek_to(100, 15, 200) == 115


def test_seek_without_length_only_stops_at_zero():
    assert seek_to(10, 5, 0) == 15
    assert seek_to(3, -5, 0) == 0


def test_volume_steps_clamp_and_round():
    assert step_volume(0.97, 0.05) == 1.0
    assert step_volume(0.02, -0.05) == 0.0
    assert step_volume(0.5, 0.05) == 0.55


def test_keys():
    assert key_action("space", False, "home") == "play-pause"
    assert key_action("Left", False, "full") == "seek-back"
    assert key_action("Right", False, "lyrics") == "seek-forward"
    assert key_action("Up", False, "home") == "volume-up"
    assert key_action("Down", False, "home") == "volume-down"
    assert key_action("n", False, "home") == key_action("N", False, "full") == "next"
    assert key_action("p", False, "lyrics") == "previous"
    assert key_action("l", False, "home") == key_action("L", False, "lyrics") == "lyrics"
    assert key_action("l", False, "full") is None
    assert key_action("f", False, "home") == key_action("F11", False, "lyrics") == "fullscreen"
    assert key_action("f", False, "full") == "fullscreen"


def test_escape_goes_back_except_home():
    assert key_action("Escape", False, "full") == "back"
    assert key_action("Escape", False, "lyrics") == "back"
    assert key_action("Escape", False, "home") is None


def test_ctrl_only_quits():
    assert key_action("q", True, "full") == "quit"
    assert key_action("Q", True, "home") == "quit"
    assert key_action("q", False, "home") is None
    assert key_action("space", True, "home") is None
    assert key_action("l", True, "home") is None
