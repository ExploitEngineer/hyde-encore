from encorelib.session import FetchGate, order_by_recency, pick_player


def test_playing_beats_paused_regardless_of_order():
    players = [("firefox.instance123", "Paused"), ("spotify", "Playing")]
    assert pick_player(players, ()) == "spotify"
    assert pick_player(list(reversed(players)), ()) == "spotify"


def test_paused_beats_stopped():
    assert pick_player([("mpv", "Stopped"), ("spotify", "Paused")], ()) == "spotify"


def test_first_playing_wins_when_several_play():
    assert pick_player([("mpv", "Playing"), ("spotify", "Playing")], ()) == "mpv"


def test_allow_list_filters_by_name_and_instance():
    players = [("chromium.instance42", "Playing"), ("spotify", "Paused")]
    assert pick_player(players, ("spotify",)) == "spotify"
    assert pick_player(players, ("chromium",)) == "chromium.instance42"


def test_none_when_nothing_matches():
    assert pick_player([], ()) is None
    assert pick_player([("mpv", "Stopped")], ()) is None
    assert pick_player([("mpv", "Playing")], ("spotify",)) is None


def test_fetch_gate_drops_stale_results():
    gate = FetchGate()
    t1 = gate.begin("A")
    t2 = gate.begin("B")
    assert gate.accept(t1, "A") is False
    assert gate.accept(t2, "B") is True


def test_fetch_gate_same_track_refetch_new_token():
    gate = FetchGate()
    t1 = gate.begin("A")
    t2 = gate.begin("A")
    assert gate.accept(t1, "A") is False
    assert gate.accept(t2, "A") is True
    assert gate.accept(t2, "B") is False


def test_order_by_recency_puts_recent_first():
    assert order_by_recency(["a", "b", "c"], ["c", "a"]) == ["c", "a", "b"]


def test_most_recently_started_player_wins_when_both_play():
    players = {"spotify": "Playing", "firefox": "Playing"}
    names = order_by_recency(list(players), ["firefox", "spotify"])
    assert pick_player([(n, players[n]) for n in names], ()) == "firefox"


def test_guarded_logs_and_returns_default():
    from encorelib.session import guarded

    @guarded(default=True)
    def tick():
        raise OSError("disk full")

    assert tick() is True


def test_guarded_passes_through_normal_result():
    from encorelib.session import guarded

    @guarded(default=None)
    def handler(x):
        return x * 2

    assert handler(4) == 8


def test_micros_to_seconds_tolerates_odd_types():
    from encorelib.session import micros_to_seconds

    assert micros_to_seconds(213_000_000) == 213.0
    assert micros_to_seconds("213000000") == 213.0
    assert micros_to_seconds(2.5e6) == 2.5
    assert micros_to_seconds(None) == 0.0
    assert micros_to_seconds("garbage") == 0.0
    assert micros_to_seconds(-5) == 0.0
