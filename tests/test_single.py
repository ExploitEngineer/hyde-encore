import os
import subprocess

from encorelib.single import claim, pid_alive, read_pid, release


def test_read_pid_garbage(tmp_path):
    p = tmp_path / "pid"
    assert read_pid(p) is None
    p.write_text("")
    assert read_pid(p) is None
    p.write_text("abc")
    assert read_pid(p) is None
    p.write_text("123\n")
    assert read_pid(p) == 123


def dead_pid() -> int:
    proc = subprocess.Popen(["true"])
    proc.wait()
    return proc.pid


def test_pid_alive_checks_marker():
    assert pid_alive(os.getpid(), marker="python") is True
    assert pid_alive(os.getpid(), marker="encore") is False
    assert pid_alive(dead_pid(), marker="python") is False


def test_claim_then_second_claim_fails(tmp_path):
    p = tmp_path / "pid"
    assert claim(p, marker="python") is True
    assert read_pid(p) == os.getpid()
    assert claim(p, marker="python") is False


def test_claim_replaces_dead_pid(tmp_path):
    p = tmp_path / "pid"
    p.write_text(str(dead_pid()))
    assert claim(p, marker="python") is True
    assert read_pid(p) == os.getpid()


def test_release_only_own_pid(tmp_path):
    p = tmp_path / "pid"
    p.write_text(str(os.getpid() + 1))
    release(p)
    assert p.exists()
    p.write_text(str(os.getpid()))
    release(p)
    assert not p.exists()
