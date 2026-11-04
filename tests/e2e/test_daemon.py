import signal
import time

import pytest

pytestmark = pytest.mark.e2e

ARTIST, TITLE = "Rick Astley", "Never Gonna Give You Up"  # fake_mpris track 1
# invented lines: a 30 s break after line 3, one CJK line
LRC = """[00:01.00]first line here
[00:03.00]second line rolls on
[00:06.00]夜に駆けるテスト
[00:09.00]last words before the break
[00:40.00]back after the break
[00:43.00]the end
"""


@pytest.fixture
def playing(harness):
    harness.write_lrc(ARTIST, TITLE, LRC)
    harness.start_player()
    daemon = harness.start_daemon()
    harness.ctl("encoretest", "play")
    harness.wait(lambda s: s["status"] == "playing" and s["lyrics"] is not None)
    harness.daemon = daemon
    return harness


def seek_paused(h, seconds):
    h.ctl("encoretest", "pause")
    h.wait(lambda s: s["status"] == "paused")
    h.ctl("encoretest", "position", str(seconds))
    return h.wait(lambda s: abs(s["position"] - seconds) < 0.05)


def test_follows_player_and_local_lyrics(playing):
    state = playing.state()
    assert state["player"] == "encoretest"
    assert state["track"]["title"] == TITLE
    assert state["lyrics"]["source"] == "local"
    assert len(state["lyrics"]["lines"]) == 6


def test_seek_lands_on_line(playing):
    state = seek_paused(playing, 12)
    assert state["line"]["index"] == 3
    state = seek_paused(playing, 6.5)
    assert state["line"]["text"] == "夜に駆けるテスト"


def test_pause_freezes_the_line(playing):
    before = seek_paused(playing, 2)
    time.sleep(1.0)  # elapsed time is what is under test, not a wait for a condition
    after = playing.state()
    assert after["position"] == before["position"]
    assert after["line"]["index"] == before["line"]["index"] == 0


def test_gap_released_after_hold(playing):
    state = seek_paused(playing, 15.5)
    assert state["line"] is None
    assert state["gap"] == {"after": 3, "until": 40.0}
    assert state["next"] == "back after the break"


def test_handover_to_newer_player(playing):
    playing.start_player("other")
    playing.ctl("other", "play")
    assert playing.wait(lambda s: s["player"] == "other")["status"] == "playing"


def test_player_vanishes_and_a_new_one_is_followed(playing):
    fake = playing.children[0]
    fake.terminate()
    fake.wait(3)
    playing.wait(lambda s: s["status"] == "stopped")
    playing.start_player()
    playing.ctl("encoretest", "play")
    playing.wait(lambda s: s["status"] == "playing" and s["track"]["title"] == TITLE)


def test_second_daemon_exits(playing):
    second = playing.start_daemon()
    assert second.wait(3) == 0
    assert playing.state()["status"] == "playing"


def test_shutdown_removes_runtime_files(playing):
    hyde = playing.run / "hyde"
    assert (hyde / "encore.sock").exists() and (hyde / "encore.track").exists()
    playing.daemon.send_signal(signal.SIGINT)
    assert playing.daemon.wait(3) == 0
    left = sorted(p.name for p in hyde.iterdir() if p.name.startswith("encore"))
    assert left == []


TRACKS = [(ARTIST, TITLE), ("The Weeknd", "Blinding Lights")]  # fake_mpris order


def test_fast_skips_end_on_last_track_with_bounded_threads(harness):
    from harness import thread_count, write_png

    for artist, title in TRACKS:
        harness.write_lrc(artist, title, f"[00:01.00]{title} line one\n[00:03.00]{title} two\n")
    cover = write_png(harness.tmp / "cover.png")
    harness.slow_wallbash(1.0)  # palette work outlives each skip, like a slow network
    harness.start_player(art=str(cover))
    daemon = harness.start_daemon()
    harness.ctl("encoretest", "play")
    harness.wait(lambda s: s["status"] == "playing" and s["lyrics"] and s["track"]["art"])
    baseline = thread_count(daemon.pid)
    peak = baseline
    skips = 6
    for _ in range(skips):
        harness.ctl("encoretest", "next")
        peak = max(peak, thread_count(daemon.pid))
    title = TRACKS[skips % len(TRACKS)][1]

    def settled(s):
        nonlocal peak
        peak = max(peak, thread_count(daemon.pid))
        lines = (s["lyrics"] or {}).get("lines") or []
        return (
            s["track"]["title"] == title
            and lines
            and lines[0]["text"].startswith(title)
            and s["track"]["art"]  # the newest track's palette job finished
        )

    harness.wait(settled, timeout=15)
    # lyrics and palette work: at most 2 + 1 workers above the idle daemon
    assert peak - baseline <= 3, (baseline, peak)
