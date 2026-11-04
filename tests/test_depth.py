from pytest import approx

from encorelib.depth import (
    DEPTH,
    browse_offset,
    edge_fades,
    line_depth,
    scroll_target,
    seek_time,
    step,
    visible_range,
)


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


def test_plain_lines_stay_sharp():
    # unsynced lyrics have no current line: every line at full depth, readable
    assert line_depth(0, -1) == 0
    assert line_depth(3, -1) == 0
    assert line_depth(3, 3) == 0
    assert line_depth(4, 3) == 1
    assert line_depth(9, 3) == 2


def test_seek_time_only_for_timed_lines():
    assert seek_time({"start": 12.5, "text": "a"}) == 12.5
    assert seek_time({"start": 0.0, "text": "a"}) == 0.0
    assert seek_time({"text": "plain"}) is None
    assert seek_time({"start": None, "text": "plain"}) is None


def test_browse_offset_clamps_to_the_song():
    tops = [0.0, 50.0, 100.0, 150.0]
    heights = [40.0] * 4
    view = 100.0
    assert browse_offset(0.0, -30.0, tops, heights, view) == 0.0
    assert browse_offset(0.0, 30.0, tops, heights, view) == 30.0
    # as far down as following the last line would go, never farther
    last = scroll_target(tops, heights, 3, view)
    assert browse_offset(100.0, 500.0, tops, heights, view) == approx(last)
    assert browse_offset(0.0, 10.0, [], [], view) == 0.0


def test_edge_fades_open_at_the_ends():
    # nothing is hidden above the top or below the end: no fade there, the
    # full fade once more than EDGE px of content lies beyond the edge
    top, bottom = edge_fades(0.0, content_h=1000.0, view_h=400.0, edge=90.0)
    assert top <= 1.0 and bottom == 90.0
    top, bottom = edge_fades(600.0, content_h=1000.0, view_h=400.0, edge=90.0)
    assert top == 90.0 and bottom <= 1.0
    top, bottom = edge_fades(45.0, content_h=1000.0, view_h=400.0, edge=90.0)
    assert top == 45.0 and bottom == 90.0
    top, bottom = edge_fades(0.0, content_h=300.0, view_h=400.0, edge=90.0)
    assert top <= 1.0 and bottom <= 1.0  # the whole song fits in the view
