from encorelib.lockscreen import DEFAULT_LAYOUT, ENCORE_LAYOUT, read_layout, with_layout


def test_read_layout():
    assert read_layout('A="1"\nHYPRLOCK_LAYOUT="Anurati"\n') == "Anurati"
    assert read_layout("HYPRLOCK_LAYOUT=Catppuccin\n") == "Catppuccin"
    assert read_layout("") is None
    assert read_layout('X_HYPRLOCK_LAYOUT="no"\n') is None


def test_with_layout_replaces_and_appends():
    assert with_layout('HYPRLOCK_LAYOUT="Anurati"\nX="1"\n', "Encore") == (
        'HYPRLOCK_LAYOUT="Encore"\nX="1"\n'
    )
    assert with_layout('X="1"\n', "Encore") == 'X="1"\nHYPRLOCK_LAYOUT="Encore"\n'
    assert with_layout("", "Encore") == 'HYPRLOCK_LAYOUT="Encore"\n'
    assert with_layout('X="1"', "Encore") == 'X="1"\nHYPRLOCK_LAYOUT="Encore"\n'


def test_names():
    assert ENCORE_LAYOUT == "Encore" and DEFAULT_LAYOUT == "HyDE"
