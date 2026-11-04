import signal
import subprocess
import sys
import time

import pytest
from harness import LIB

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
    # the lookup journal outlives a restart on purpose: it explains missing lyrics
    assert left == ["encore.lookups"]


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


def test_rate_is_followed(playing):
    playing.set_rate("encoretest", 1.5)
    state = playing.wait(lambda s: s["rate"] == 1.5)
    time.sleep(1.0)  # let the player run at 1.5x
    before = time.monotonic()
    player_pos = float(playing.ctl("encoretest", "position"))
    after = time.monotonic()
    # the player answered somewhere inside the playerctl call: compare at its middle
    # and allow for the half-call uncertainty at 1.5x
    daemon_pos = state["position"] + ((before + after) / 2 - state["ts"]) * state["rate"]
    slack = 0.15 + (after - before) / 2 * state["rate"]
    assert abs(daemon_pos - player_pos) < slack, (daemon_pos, player_pos, slack)


def test_bad_rate_falls_back_to_one(playing):
    playing.set_rate("encoretest", 1.5)
    playing.wait(lambda s: s["rate"] == 1.5)
    playing.set_rate("encoretest", 0.0)
    assert playing.wait(lambda s: s["rate"] == 1.0)["status"] == "playing"


def test_polling_while_paused_does_not_leak_fds(playing):
    import os

    seek_paused(playing, 5.0)
    fds = lambda: len(os.listdir(f"/proc/{playing.daemon.pid}/fd"))
    before = fds()
    for _ in range(300):  # two minutes of the player window's 400 ms polling
        assert playing.state()["status"] == "paused"
    assert fds() - before < 10


def test_lookups_are_journaled(playing):
    import json

    rows = [
        json.loads(line)
        for line in (playing.run / "hyde" / "encore.lookups").read_text().splitlines()
    ]
    assert rows[-1]["title"] == TITLE and rows[-1]["result"] == "local/line"


def run_cli(h, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(LIB / "encore.py"), *args],
        env=h.env,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )


def test_state_lists_players_newest_first(harness):
    harness.start_player("encoretest")
    harness.start_player("encoretest2")
    harness.start_daemon()
    harness.ctl("encoretest", "play")
    harness.wait(lambda s: s["player"] == "encoretest")
    harness.ctl("encoretest2", "play")
    state = harness.wait(lambda s: (s.get("players") or [""])[0] == "encoretest2")
    assert sorted(state["players"]) == ["encoretest", "encoretest2"]


def test_volume_published_and_follows_changes(playing):
    playing.wait(lambda s: s["volume"] == 1.0)
    playing.ctl("encoretest", "volume", "0.4")
    playing.wait(lambda s: s["volume"] == 0.4)


def test_volume_null_when_player_has_none(harness):
    harness.start_player("encoretest", "", "--no-volume")
    harness.start_daemon()
    harness.ctl("encoretest", "play")
    harness.wait(lambda s: s["status"] == "playing")
    # Rate is read through the same proxy as Volume: once it shows, the proxy is live
    harness.set_rate("encoretest", 1.5)
    state = harness.wait(lambda s: s["rate"] == 1.5)
    assert state["volume"] is None


def test_follow_pin_switches_and_clears(harness):
    harness.start_player("encoretest")
    second = harness.start_player("encoretest2")
    harness.start_daemon()
    harness.ctl("encoretest", "play")
    harness.wait(lambda s: s["player"] == "encoretest")
    assert run_cli(harness, "follow", "encoretest2").returncode == 0
    harness.wait(lambda s: s["player"] == "encoretest2")
    follow = harness.run / "hyde" / "encore.follow"
    assert follow.read_text().strip() == "encoretest2"
    second.terminate()
    second.wait(timeout=5)
    harness.wait(lambda s: s["player"] == "encoretest")
    harness.wait_until(lambda: not follow.exists(), "the pin to clear")


def test_follow_auto_removes_pin(harness):
    harness.start_player("encoretest")
    harness.start_player("encoretest2")
    harness.start_daemon()
    harness.ctl("encoretest", "play")
    run_cli(harness, "follow", "encoretest2")
    harness.wait(lambda s: s["player"] == "encoretest2")
    assert run_cli(harness, "follow", "auto").returncode == 0
    harness.wait(lambda s: s["player"] == "encoretest")
    assert not (harness.run / "hyde" / "encore.follow").exists()
