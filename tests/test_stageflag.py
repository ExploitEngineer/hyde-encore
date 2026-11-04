from encorelib.stageflag import covers, render


def test_render_names_output_and_app():
    assert render("eDP-1", 4242) == "eDP-1\n4242\n"


def test_covers_matching_output_while_the_app_lives():
    assert covers("eDP-1\n4242\n", "eDP-1", lambda pid: pid == 4242) is True
    assert covers("*\n4242\n", "eDP-1", lambda pid: pid == 4242) is True  # output not known yet
    assert covers("HDMI-A-1\n4242\n", "eDP-1", lambda pid: True) is False
    assert covers("eDP-1\n4242\n", "", lambda pid: True) is True  # overlay on any output


def test_dead_app_does_not_cover():
    assert covers("eDP-1\n4242\n", "eDP-1", lambda pid: False) is False


def test_old_or_empty_flags_do_not_cover():
    assert covers("eDP-1\n", "eDP-1", lambda pid: True) is False  # no pid: unknown app
    assert covers("", "eDP-1", lambda pid: True) is False
    assert covers("eDP-1\nnope\n", "eDP-1", lambda pid: True) is False
