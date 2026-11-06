"""'encore lock' against a stub hyde-shell and a private HyDE state file."""

import os
import stat
import subprocess
import sys

import pytest
from harness import LIB

pytestmark = pytest.mark.e2e


@pytest.fixture
def hyde(tmp_path):
    """A stub hyde-shell first on PATH that logs its arguments, plus a state dir."""
    bins = tmp_path / "bin"
    bins.mkdir()
    log = tmp_path / "hyde-shell.log"
    stub = bins / "hyde-shell"
    stub.write_text(f'#!/bin/sh\necho "$@" >> "{log}"\n')
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    state = tmp_path / "state" / "hyde"
    state.mkdir(parents=True)
    (state / "staterc").write_text('HYPRLOCK_LAYOUT="Anurati"\nWALLPAPER="x"\n')
    env = {k: v for k, v in os.environ.items() if not k.startswith("ENCORE_")}
    env.update(
        PATH=f"{bins}:{env.get('PATH', '')}",
        XDG_STATE_HOME=str(tmp_path / "state"),
        XDG_RUNTIME_DIR=str(tmp_path / "run"),
        XDG_CACHE_HOME=str(tmp_path / "cache"),
    )
    (tmp_path / "run").mkdir()

    def lock(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(LIB / "encore.py"), "lock", *args],
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )

    return lock, state / "staterc", log


def test_lock_on_off_restores_previous(hyde):
    lock, staterc, log = hyde
    assert lock("status").stdout.strip() == "off"
    assert lock("on").returncode == 0
    assert 'HYPRLOCK_LAYOUT="Encore"' in staterc.read_text()
    assert "WALLPAPER" in staterc.read_text()  # the rest of the file is kept
    assert lock("status").stdout.strip() == "on"
    assert lock("off").returncode == 0
    assert 'HYPRLOCK_LAYOUT="Anurati"' in staterc.read_text()
    assert lock("status").stdout.strip() == "off"
    assert log.read_text().splitlines() == ["hyprlock.sh --reload", "hyprlock.sh --reload"]


def test_lock_on_twice_keeps_the_real_previous(hyde):
    lock, staterc, _log = hyde
    lock("on")
    lock("on")
    lock("off")
    assert 'HYPRLOCK_LAYOUT="Anurati"' in staterc.read_text()


def test_lock_off_without_previous_uses_the_default(hyde):
    lock, staterc, _log = hyde
    staterc.write_text('HYPRLOCK_LAYOUT="Encore"\n')  # chosen by hand, nothing remembered
    lock("off")
    assert 'HYPRLOCK_LAYOUT="HyDE"' in staterc.read_text()


def test_lock_preview_runs_the_test_layout(hyde):
    lock, _staterc, log = hyde
    assert lock("preview").returncode == 0
    assert log.read_text().splitlines() == ["hyprlock.sh --test Encore"]
