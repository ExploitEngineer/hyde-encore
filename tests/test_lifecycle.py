from encorelib.lifecycle import close_action


def test_close_action():
    assert close_action(False, False) == "quit"
    assert close_action(True, False) == "hide"
    assert close_action(False, True) == "hide"
    assert close_action(True, True) == "hide"
