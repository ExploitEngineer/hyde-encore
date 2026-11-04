from itertools import pairwise

from encorelib.motion import blob_center, ease_in_out, ease_out, grain_texture_bytes, lerp


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
