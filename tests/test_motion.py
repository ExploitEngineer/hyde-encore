from itertools import pairwise

import pytest

from encorelib.motion import (
    FIELD_FPS,
    blob_center,
    ease_in_out,
    ease_out,
    field_rate,
    ghosts,
    grain_texture_bytes,
    lerp,
    pop_in,
    settle_curve,
    spring,
)


def test_ease_out_is_monotonic_and_bounded():
    xs = [ease_out(i / 20) for i in range(21)]
    assert xs[0] == 0 and xs[-1] == 1
    assert all(b >= a for a, b in pairwise(xs))
    assert ease_out(0.5) > 0.5  # fast start, soft landing
    assert ease_out(-1) == 0 and ease_out(2) == 1  # clamped


def test_ease_in_out_is_symmetric():
    assert ease_in_out(0) == 0 and ease_in_out(1) == 1
    assert abs(ease_in_out(0.5) - 0.5) < 1e-9
    assert abs(ease_in_out(0.25) + ease_in_out(0.75) - 1) < 1e-9


def test_lerp():
    assert lerp(10, 20, 0.25) == 12.5
    assert lerp(10, 20, 0) == 10 and lerp(10, 20, 1) == 20


def test_blob_center_stays_inside():
    for t in range(0, 120, 7):
        x, y = blob_center(t, (0.22, 0.16), (41.0, 29.0), 0.0)
        assert 0.28 <= x <= 0.72 and 0.34 <= y <= 0.66


def test_grain_texture_is_fine_and_faint():
    data = grain_texture_bytes(128, seed=7)
    assert len(data) == 128 * 128 * 4
    alphas = data[3::4]
    assert 2 < sum(alphas) / len(alphas) < 8  # faint on average (about 2% white)
    assert max(alphas) <= 14  # never a bright speck
    assert grain_texture_bytes(128, seed=7) == data  # stable across runs
    assert grain_texture_bytes(128, seed=8) != data


def test_held_scale_caps():
    from encorelib.motion import held_scale

    assert held_scale(0.1) == 1.0 and held_scale(0.3) == 1.0
    assert abs(held_scale(0.75) - 1.09) < 0.01
    assert held_scale(1.2) == 1.18 and held_scale(8.0) == 1.18


def test_field_rate_holds_when_paused():
    # the field drifts while music plays, or while nothing plays at all (the
    # idle light); a paused track holds, with or without a cover
    assert field_rate(playing=True, idle=False) == FIELD_FPS
    assert field_rate(playing=False, idle=True) == FIELD_FPS
    assert field_rate(playing=False, idle=False) == 0
    assert FIELD_FPS >= 1


def test_spring_ends():
    assert spring(0) == 0.0 and spring(-1) == 0.0
    assert spring(0.32) == 1.0 and spring(5) == 1.0
    assert spring(0.24, settle=0.24) == 1.0


def test_spring_overshoots_then_settles():
    ts = [i / 1000 for i in range(321)]
    xs = [spring(t) for t in ts]
    peak = max(xs)
    assert 1.05 <= peak <= 1.15  # a visible pop
    assert ts[xs.index(peak)] <= 0.6 * 0.32
    assert all(-0.01 <= x <= 1.2 for x in xs)  # bounded
    assert abs(spring(0.32 - 1e-6) - 1) <= 0.01  # within 1% by settle: the clamp never jumps


def test_spring_final_approach_is_monotonic():
    # after the last extremum before settle the curve only closes in on 1
    ts = [0.32 * (0.87 + i / 1000) for i in range(131)]
    xs = [spring(t) for t in ts]
    assert all(b >= a - 1e-9 for a, b in pairwise(xs))


def test_ghosts_swell_mid_slide_and_vanish_when_settled():
    assert ghosts(0.0) == [] and ghosts(1.0) == [] and ghosts(1.4) == [] and ghosts(-0.2) == []
    mid = ghosts(0.5)
    assert [lag for lag, _ in mid] == [0.055, 0.110]
    assert mid[0][1] == pytest.approx(0.35) and mid[1][1] == pytest.approx(0.18)
    assert ghosts(0.1)[0][1] < mid[0][1]
    assert len(ghosts(0.5, count=1)) == 1
    assert ghosts(0.5, count=0) == []


def test_settle_curve_without_motion_is_a_plain_ease():
    assert settle_curve(0.08, False, 0.24) == pytest.approx(ease_out(0.5))
    assert settle_curve(0.16, False, 0.24) == 1.0
    assert settle_curve(0.1, True, 0.24) == pytest.approx(spring(0.1, 0.24))
    assert settle_curve(-1, True, 0.24) == 0.0


def test_pop_in_grows_from_six_tenths_with_a_visible_overshoot():
    assert pop_in(0.0, True) == (0.0, 0.6)
    assert pop_in(1.0, True) == (1.0, 1.0)
    scales = [pop_in(i / 1000, True)[1] for i in range(330)]
    assert max(scales) > 1.03  # the overshoot shows
    alphas = [pop_in(i / 1000, True)[0] for i in range(330)]
    assert all(0.0 <= a <= 1.0 for a in alphas)


def test_pop_in_without_motion_never_overshoots():
    scales = [pop_in(i / 1000, False)[1] for i in range(200)]
    assert max(scales) == 1.0 and min(scales) == 0.6
