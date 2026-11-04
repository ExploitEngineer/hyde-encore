import os

import pytest

pytestmark = pytest.mark.e2e


def test_harness_is_private(harness):
    real_runtime = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    assert str(harness.socket).startswith(f"/run/user/{os.getuid()}/enc-")
    assert not str(harness.socket).startswith(f"{real_runtime}/hyde")
    assert harness.env["DBUS_SESSION_BUS_ADDRESS"] != os.environ.get("DBUS_SESSION_BUS_ADDRESS")
    assert len(str(harness.socket).encode()) < 108  # AF_UNIX path limit


def test_daemon_reports_stopped_without_players(harness):
    harness.start_daemon()
    assert harness.wait(lambda s: s["status"] == "stopped")["track"] is None


def test_harness_cleans_up(tmp_path):
    from harness import Harness

    with Harness(tmp_path) as h:
        h.start_player()
        h.start_daemon()
        h.wait(lambda s: s["status"] in ("paused", "stopped"))
        children = [h.bus, *h.children]
        run_dir = h.run
    assert all(p.poll() is not None for p in children)
    assert not run_dir.exists()


def test_harness_creates_missing_base_dirs(tmp_path):
    from harness import Harness

    with Harness(tmp_path / "not" / "yet") as h:
        assert (tmp_path / "not" / "yet" / "lyrics").is_dir()
        assert h.run.is_dir()


def test_failed_setup_stops_the_bus(tmp_path, monkeypatch):
    import harness as module

    def boom(**_kw):
        raise OSError("no runtime dir")

    monkeypatch.setattr(module.tempfile, "mkdtemp", boom)
    h = module.Harness(tmp_path)
    with pytest.raises(OSError):
        h.__enter__()
    assert h.bus.poll() is not None
