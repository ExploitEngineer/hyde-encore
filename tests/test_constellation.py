import itertools
import math

from encorelib.constellation import chain_words, place_words, sparkles

WORDS = ["We're", "no", "strangers", "to", "love", "you", "know", "the", "rules"]


def test_deterministic_for_same_seed():
    a = place_words(WORDS, 1920, 1080, seed="cafe01:3")
    b = place_words(WORDS, 1920, 1080, seed="cafe01:3")
    assert a == b


def test_different_seeds_differ():
    a = place_words(WORDS, 1920, 1080, seed="cafe01:3")
    b = place_words(WORDS, 1920, 1080, seed="beef02:3")
    assert a != b


def test_one_position_per_word_inside_margins():
    pos = place_words(WORDS, 1920, 1080, seed="x", margin=140)
    assert len(pos) == len(WORDS)
    for x, y in pos:
        assert 140 <= x <= 1920 - 140
        assert 140 <= y <= 1080 - 140


def test_pairwise_min_distance():
    pos = place_words(WORDS, 1920, 1080, seed="x", min_dist=120)
    for i, (xa, ya) in enumerate(pos):
        for xb, yb in pos[i + 1 :]:
            assert math.hypot(xa - xb, ya - yb) >= 120 * 0.6  # relaxed only under fallback


def test_meanders_left_to_right():
    pos = place_words(WORDS, 1920, 1080, seed="x")
    xs = [x for x, _ in pos]
    assert xs[0] < xs[-1]


def test_tiny_screen_still_places_everything():
    pos = place_words(WORDS * 3, 400, 240, seed="x", margin=20, min_dist=60)
    assert len(pos) == len(WORDS) * 3


def test_sparkles_deterministic_and_bounded():
    a = sparkles("k1", 1920, 1080, k=7)
    assert a == sparkles("k1", 1920, 1080, k=7)
    assert len(a) == 7
    assert all(0 <= x <= 1920 and 0 <= y <= 1080 for x, y in a)


def test_chain_words_deterministic_and_stepped():
    from encorelib.constellation import chain_words

    a = chain_words(WORDS, 1920, 1080, seed="k1")
    assert a == chain_words(WORDS, 1920, 1080, seed="k1")
    assert a != chain_words(WORDS, 1920, 1080, seed="k2")
    assert len(a) == len(WORDS)
    import math

    steps = [math.hypot(b[0] - c[0], b[1] - c[1]) for b, c in itertools.pairwise(a)]
    # near the previous word, never on it; steps scale with the screen height
    assert all(1080 * 0.105 <= s <= 1080 * 0.27 for s in steps), steps


def test_chain_steps_scale_with_the_screen():
    import math

    big = chain_words(WORDS, 3840, 2160, seed="k1")
    steps = [math.hypot(b[0] - c[0], b[1] - c[1]) for b, c in itertools.pairwise(big)]
    assert min(steps) >= 2160 * 0.105


def test_chain_words_stay_in_center_band():
    from encorelib.constellation import chain_words

    pos = chain_words(WORDS * 3, 1920, 1080, seed="k1")
    for x, y in pos:
        assert 1920 * 0.12 <= x <= 1920 * 0.88
        assert 1080 * 0.2 <= y <= 1080 * 0.8


def test_chain_is_centered_on_screen():
    for seed in ("a", "line 2", "line 3", "x9"):
        pts = chain_words(["w"] * 6, 1920, 1080, seed=seed)
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        assert abs((min(xs) + max(xs)) / 2 - 960) < 60
        assert abs((min(ys) + max(ys)) / 2 - 540) < 60


def test_short_line_is_centered_too():
    pts = chain_words(["only", "two"], 1920, 1080, seed="short")
    assert abs((pts[0][0] + pts[1][0]) / 2 - 960) < 60
