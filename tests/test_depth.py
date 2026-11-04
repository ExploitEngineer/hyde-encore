from pytest import approx

from encorelib.depth import DEPTH, scroll_target, step, visible_range


def test_depth_steps_cap():
    assert [step(d) for d in (0, 1, 2, 3, 40)] == [0, 1, 2, 2, 2]
    assert [step(d) for d in (-1, -2, -9)] == [1, 2, 2]  # past lines recede the same way
    assert DEPTH[0] == (1.0, 1.0, 0.0)
    assert DEPTH[1] == (0.94, 0.55, 1.5)
    assert DEPTH[2] == (0.9, 0.32, 3.0)


def test_scroll_target_keeps_current_at_anchor():
    tops = [0, 60, 120, 180, 240, 300]
    heights = [50] * 6
    # the current line's center sits at 38% of the view
    assert scroll_target(tops, heights, 3, 400) == approx(180 + 25 - 0.38 * 400)
    assert scroll_target(tops, heights, 0, 400) == 0  # never above the top
    assert scroll_target(tops, heights, -1, 400) == 0  # no current line: the top


def test_scroll_target_never_past_the_end():
    tops = [0, 60, 120]
    heights = [50] * 3
    # content is 170 tall in a 400 view: nothing to scroll
    assert scroll_target(tops, heights, 2, 400) == 0


def test_visible_range_with_one_line_of_slack():
    tops = [i * 60 for i in range(50)]
    heights = [50] * 50
    first, last = visible_range(tops, heights, scroll=600, view_h=400)
    assert first == 9 and last == 17  # lines 10..16 are in view, plus one each side
    assert visible_range(tops, heights, 0, 400) == (0, 7)
    assert visible_range(tops, heights, 10_000, 400) == (49, 49)
