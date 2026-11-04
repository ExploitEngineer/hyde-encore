from encorelib.dbusmenu import ACTIONS, layout


def ids(tree):
    return [child[0] for child in tree[2]]


def props(tree, item_id):
    return next(child[1] for child in tree[2] if child[0] == item_id)


def test_layout_ids_and_labels():
    tree = layout(desktop_on=False, glow_on=False, playing=False)
    assert tree[0] == 0 and tree[1] == {"children-display": "submenu"}
    assert ids(tree) == [1, 2, 3, 4, 5, 6, 7]
    assert props(tree, 1)["label"] == "Open Encore"
    assert props(tree, 3)["label"] == "Next"
    assert props(tree, 6) == {"type": "separator"}
    assert props(tree, 7)["label"] == "Quit"
    assert all(child[2] == [] for child in tree[2])


def test_toggle_states_follow_the_surfaces():
    on = layout(desktop_on=True, glow_on=False, playing=False)
    assert props(on, 4)["toggle-type"] == "checkmark" and props(on, 4)["toggle-state"] == 1
    assert props(on, 5)["toggle-type"] == "checkmark" and props(on, 5)["toggle-state"] == 0
    off = layout(desktop_on=False, glow_on=True, playing=False)
    assert props(off, 4)["toggle-state"] == 0 and props(off, 5)["toggle-state"] == 1


def test_play_label_follows_status():
    assert props(layout(False, False, playing=True), 2)["label"] == "Pause"
    assert props(layout(False, False, playing=False), 2)["label"] == "Play"


def test_actions_cover_every_item_but_the_separator():
    assert ACTIONS == {
        1: "open",
        2: "play-pause",
        3: "next",
        4: "desktop",
        5: "glow",
        7: "quit",
    }
