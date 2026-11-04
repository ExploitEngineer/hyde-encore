"""Isolated end-to-end harness for the encore daemon.

Starts a private session bus, a short private runtime dir under
/run/user/$UID (AF_UNIX socket paths cap at 108 bytes), private cache,
state and lyrics dirs, fake MPRIS players and the repo's daemon, all as
subprocesses. Nothing touches the owner's session: their players live on
another bus and their encore.sock in another dir. The test process never
imports gi; it drives players with playerctl and reads encore.sock.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Self

REPO = Path(__file__).resolve().parents[2]
LIB = REPO / "Configs" / ".local" / "lib" / "hyde"
FAKE = Path(__file__).with_name("fake_mpris.py")
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

from encorelib.protocol import read_state

STOP_TIMEOUT = 3.0
POLL_SECONDS = 0.05


def missing_requirement() -> str | None:
    """Why the harness cannot run here, or None."""
    for tool in ("dbus-daemon", "playerctl"):
        if shutil.which(tool) is None:
            return f"{tool} is not installed"
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            "import gi; gi.require_version('Playerctl', '2.0'); from gi.repository import Playerctl",
        ],
        capture_output=True,
        check=False,
    )
    if probe.returncode != 0:
        return "PyGObject with Playerctl 2.0 is not available"
    return None


def _stop(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(STOP_TIMEOUT)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


class Harness:
    def __init__(self, tmp_path: Path):
        self.tmp = Path(tmp_path)
        self.bus: subprocess.Popen | None = None
        self.children: list[subprocess.Popen] = []
        self.run: Path | None = None
        self.env: dict[str, str] = {}

    # lifecycle ---------------------------------------------------------------

    def __enter__(self) -> Self:
        try:
            self._setup()
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def _setup(self) -> None:
        self.bus = subprocess.Popen(
            ["dbus-daemon", "--session", "--nofork", "--print-address=1"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        address = self.bus.stdout.readline().strip()
        if not address:
            _stop(self.bus)
            raise RuntimeError("dbus-daemon printed no address")
        base = Path(f"/run/user/{os.getuid()}")
        self.run = Path(tempfile.mkdtemp(prefix="enc-", dir=base if base.is_dir() else None))
        for name in ("cache", "state", "lyrics", "logs"):
            (self.tmp / name).mkdir(parents=True, exist_ok=True)
        env = {k: v for k, v in os.environ.items() if not k.startswith("ENCORE_")}
        env.update(
            DBUS_SESSION_BUS_ADDRESS=address,
            XDG_RUNTIME_DIR=str(self.run),
            XDG_CACHE_HOME=str(self.tmp / "cache"),
            XDG_STATE_HOME=str(self.tmp / "state"),
            ENCORE_LYRICS_DIRS=str(self.tmp / "lyrics"),
            ENCORE_LYRICS_LRCLIB="false",  # tests never reach the network
            ENCORE_LYRICS_SPICY_KEY="",
            SPICY_LYRICS_SECRET_KEY="",
        )
        self.env = env

    def __exit__(self, *_exc) -> None:
        for process in reversed(self.children):
            _stop(process)
        _stop(self.bus)
        if self.bus is not None and self.bus.stdout is not None:
            self.bus.stdout.close()
        if self.run is not None:
            shutil.rmtree(self.run, ignore_errors=True)

    # processes ---------------------------------------------------------------

    def _spawn(self, command: list[str], log: str) -> subprocess.Popen:
        with open(self.tmp / "logs" / log, "ab") as out:
            process = subprocess.Popen(command, env=self.env, stdout=out, stderr=subprocess.STDOUT)
        self.children.append(process)
        return process

    def start_player(
        self, name: str = "encoretest", art: str = "", *extra: str
    ) -> subprocess.Popen:
        command = [sys.executable, str(FAKE), "--name", name, *extra]
        if art:
            command += ["--art", art]
        process = self._spawn(command, f"player-{name}.log")
        self.wait_until(lambda: name in self.players(), f"player {name} on the bus")
        return process

    def start_daemon(self) -> subprocess.Popen:
        return self._spawn([sys.executable, str(LIB / "encore.py"), "daemon"], "daemon.log")

    def log(self, name: str = "daemon.log") -> str:
        path = self.tmp / "logs" / name
        return path.read_text(errors="replace") if path.exists() else ""

    # observation and control -----------------------------------------------------

    @property
    def socket(self) -> Path:
        return self.run / "hyde" / "encore.sock"

    def players(self) -> list[str]:
        out = subprocess.run(
            ["playerctl", "--list-all"],
            env=self.env,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        return out.stdout.split()

    def ctl(self, name: str, *args: str) -> str:
        out = subprocess.run(
            ["playerctl", "-p", name, *args],
            env=self.env,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        return out.stdout.strip()

    def state(self) -> dict | None:
        return read_state(self.socket)

    def wait_until(self, condition: Callable[[], bool], what: str, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while not condition():
            if time.monotonic() > deadline:
                raise AssertionError(f"timed out waiting for {what}")
            time.sleep(POLL_SECONDS)

    def wait(self, predicate: Callable[[dict], bool], timeout: float = 5.0) -> dict:
        """The first daemon state matching predicate; fails with the last state seen."""
        deadline = time.monotonic() + timeout
        last = None
        while True:
            last = self.state()
            if last is not None and predicate(last):
                return last
            if time.monotonic() > deadline:
                raise AssertionError(f"timed out; last state: {last}\n{self.log()[-2000:]}")
            time.sleep(POLL_SECONDS)

    def write_lrc(self, artist: str, title: str, text: str) -> Path:
        path = self.tmp / "lyrics" / f"{artist} - {title}.lrc"
        path.write_text(text, encoding="utf-8")
        return path
