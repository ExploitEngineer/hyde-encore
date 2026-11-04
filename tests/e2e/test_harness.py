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


SIGTERM_CHILD = """
import os, signal, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from harness import Harness
with Harness(Path(sys.argv[2])) as h:
    h.start_player()
    h.start_daemon()
    h.wait(lambda s: s["status"] in ("paused", "stopped"))
    pids = [h.bus.pid] + [p.pid for p in h.children]
    print(" ".join(map(str, pids)), h.run, flush=True)
    os.kill(os.getpid(), signal.SIGTERM)  # a CI timeout or a closed terminal
    signal.pause()
"""


def test_sigterm_on_the_test_process_leaves_nothing(tmp_path):
    import subprocess
    import sys
    import time
    from pathlib import Path

    here = str(Path(__file__).resolve().parent)
    out = subprocess.run(
        [sys.executable, "-c", SIGTERM_CHILD, here, str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,  # the child dies by SIGTERM on purpose
    ).stdout.split()
    pids, run_dir = [int(p) for p in out[:-1]], Path(out[-1])

    def alive(pid):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        return Path(f"/proc/{pid}/stat").read_text().split(")")[1].split()[0] != "Z"

    deadline = time.monotonic() + 5
    while any(alive(p) for p in pids) and time.monotonic() < deadline:
        time.sleep(0.05)
    leftovers = [p for p in pids if alive(p)]
    for pid in leftovers:  # never leave strays on the owner's machine
        os.kill(pid, 9)
    assert leftovers == []
    assert not run_dir.exists()
