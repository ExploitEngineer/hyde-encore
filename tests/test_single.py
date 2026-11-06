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
    assert claim(p) is True
    assert read_pid(p) == os.getpid()
    assert claim(p) is False  # the lock is held, even within one process


def test_claim_ignores_stale_pidfile_without_lock(tmp_path):
    p = tmp_path / "pid"
    p.write_text(str(dead_pid()))
    assert claim(p) is True
    assert read_pid(p) == os.getpid()


def test_concurrent_claims_one_winner(tmp_path):
    p = tmp_path / "pid"
    code = (
        "import sys; from encorelib.single import claim; sys.exit(0 if claim(sys.argv[1]) else 1)"
    )
    holder = (
        "import sys, time; from encorelib.single import claim; "
        "ok = claim(sys.argv[1]); time.sleep(1); sys.exit(0 if ok else 1)"
    )
    env = dict(os.environ, PYTHONPATH="Configs/.local/lib/hyde")
    first = subprocess.Popen(["python3", "-c", holder, str(p)], env=env)
    # the holder keeps the lock while it sleeps; a second claim must fail
    import time

    time.sleep(0.4)
    second = subprocess.run(["python3", "-c", code, str(p)], check=False, env=env)
    assert second.returncode == 1
    first.wait()


def test_release_only_own_claim(tmp_path):
    p = tmp_path / "pid"
    p.write_text(str(os.getpid() + 1))
    release(p)  # not ours: left alone
    assert p.exists()
    p.unlink()
    claim(p)
    release(p)
    assert not p.exists()


def test_claim_holds_the_lock_when_the_pid_cannot_be_written(tmp_path, monkeypatch):
    # a full runtime dir (ENOSPC) must not make a surface think another one
    # runs: the flock is the lock, the pid text is a courtesy
    import errno

    from encorelib import single

    def full(_handle):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(single, "_record", full)
    p = tmp_path / "pid"
    assert claim(p) is True
    assert claim(p) is False  # the lock is held
    release(p)
    monkeypatch.undo()
    assert claim(p) is True
