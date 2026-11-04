import pytest

from encorelib.clock import PlaybackClock, clean_rate


class FakeTime:
    def __init__(self, t: float = 1000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def now():
    return FakeTime()


def test_advances_while_playing(now):
    clock = PlaybackClock(now)
    clock.sync(10.0, True)
    now.t += 2.5
    assert clock.position() == pytest.approx(12.5)


def test_frozen_while_paused(now):
    clock = PlaybackClock(now)
    clock.sync(10.0, False)
    now.t += 5
    assert clock.position() == 10.0
    assert clock.playing is False


def test_rate(now):
    clock = PlaybackClock(now)
    clock.sync(10.0, True, rate=2.0)
    now.t += 1
    assert clock.position() == pytest.approx(12.0)


def test_resync_jump(now):
    clock = PlaybackClock(now)
    clock.sync(10.0, True)
    now.t += 1
    clock.sync(100.0, True)
    assert clock.position() == 100.0


def test_anchor(now):
    clock = PlaybackClock(now)
    clock.sync(42.0, True)
    assert clock.anchor() == (42.0, 1000.0)


def test_starts_stopped_at_zero(now):
    clock = PlaybackClock(now)
    now.t += 3
    assert clock.position() == 0.0
    assert clock.playing is False


def test_clean_rate():
    assert clean_rate(1.5) == 1.5
    assert clean_rate(0.5) == 0.5
    for bad in (0, -1, float("nan"), float("inf"), 9, "x", None):
        assert clean_rate(bad) == 1.0


def test_sync_keeps_rate_when_omitted(now):
    clock = PlaybackClock(now)
    clock.sync(10.0, True, 1.5)
    clock.sync(10.0, True)  # a resync that does not know the rate
    now.t += 2.0
    assert clock.rate == 1.5
    assert clock.position() == pytest.approx(13.0)


def test_sync_cleans_bad_rate(now):
    clock = PlaybackClock(now)
    clock.sync(10.0, True, 0.0)
    assert clock.rate == 1.0
