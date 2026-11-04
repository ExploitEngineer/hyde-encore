import pytest

from encorelib.glowfield import COMETS, comet_strength, edge_mix, falloff_stops, perimeter_u


def test_perimeter_runs_clockwise_from_top_left():
    w, h = 1920, 1080
    total = 2 * (w + h)
    assert perimeter_u("top", 0.0, w, h) == 0.0
    assert perimeter_u("top", 1.0, w, h) == pytest.approx(w / total)
    assert perimeter_u("right", 0.0, w, h) == pytest.approx(w / total)
    assert perimeter_u("right", 1.0, w, h) == pytest.approx((w + h) / total)
    # bottom and left run right-to-left and bottom-to-top along their strips
    assert perimeter_u("bottom", 1.0, w, h) == pytest.approx((w + h) / total)
    assert perimeter_u("bottom", 0.0, w, h) == pytest.approx((2 * w + h) / total)
    assert perimeter_u("left", 0.0, w, h) == pytest.approx(0.0, abs=1e-9)


def test_comet_peaks_on_its_head_and_wraps():
    assert comet_strength(0.25, phase=0.25) == pytest.approx(1.0)
    assert comet_strength(0.25 + 0.5, phase=0.25) == pytest.approx(1.0)  # second comet
    assert comet_strength(0.5, phase=0.25) < 0.05  # halfway between the two
    assert comet_strength(0.99, phase=0.01) > 0.5  # wraps across u = 0
    assert COMETS == 2


def test_edge_mix_flows_between_colors():
    values = [edge_mix(u / 20, phase=0.0) for u in range(21)]
    assert min(values) == pytest.approx(0.0, abs=0.02)
    assert max(values) == pytest.approx(1.0, abs=0.02)
    assert edge_mix(0.3, phase=0.1) != edge_mix(0.3, phase=0.2)


def test_falloff_is_bright_at_the_edge_and_gone_inside():
    stops = falloff_stops(0.8)
    assert stops[0] == (0.0, pytest.approx(0.8))
    assert stops[-1] == (1.0, 0.0)
    alphas = [a for _, a in stops]
    assert alphas == sorted(alphas, reverse=True)
