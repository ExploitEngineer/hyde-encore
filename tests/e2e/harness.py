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
import signal
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
# children die with the test process even if it is SIGKILLed
_PDEATHSIG = ["setpriv", "--pdeathsig", "TERM", "--"] if shutil.which("setpriv") else []


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
        self._handlers: dict[int, object] = {}

    # lifecycle ---------------------------------------------------------------

    def __enter__(self) -> Self:
        self._trap_signals()
        try:
            self._setup()
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def _setup(self) -> None:
        self.bus = subprocess.Popen(
            [*_PDEATHSIG, "dbus-daemon", "--session", "--nofork", "--print-address=1"],
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
        # WAYLAND_DISPLAY is relative to XDG_RUNTIME_DIR, which changes below: pin the
        # real socket, and drop DISPLAY so GTK fails closed instead of opening an
        # X11 window on the owner's screen
        wayland = env.get("WAYLAND_DISPLAY", "")
        if wayland and not wayland.startswith("/"):
            real_runtime = env.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
            env["WAYLAND_DISPLAY"] = f"{real_runtime}/{wayland}"
        env.pop("DISPLAY", None)
        env.update(
            DBUS_SESSION_BUS_ADDRESS=address,
            XDG_RUNTIME_DIR=str(self.run),
            XDG_CACHE_HOME=str(self.tmp / "cache"),
            XDG_STATE_HOME=str(self.tmp / "state"),
            ENCORE_LYRICS_DIRS=str(self.tmp / "lyrics"),
            ENCORE_LYRICS_LRCLIB="false",  # tests never reach the network
            ENCORE_HD_COVERS="false",  # no Apple lookups either
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
        for signum, handler in self._handlers.items():
            signal.signal(signum, handler)
        self._handlers.clear()

    def _trap_signals(self) -> None:
        """SIGTERM/SIGHUP (CI timeout, closed terminal) unwind the with block, so teardown runs."""
        import threading

        if threading.current_thread() is not threading.main_thread():
            return

        def unwind(signum, _frame):
            raise SystemExit(128 + signum)

        for signum in (signal.SIGTERM, signal.SIGHUP):
            if signal.getsignal(signum) == signal.SIG_DFL:
                self._handlers[signum] = signal.signal(signum, unwind)

    # processes ---------------------------------------------------------------

    def _spawn(self, command: list[str], log: str) -> subprocess.Popen:
        with open(self.tmp / "logs" / log, "ab") as out:
            process = subprocess.Popen(
                [*_PDEATHSIG, *command], env=self.env, stdout=out, stderr=subprocess.STDOUT
            )
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

    def slow_wallbash(self, seconds: float) -> None:
        """Make album palette work slow (a stub wallbash.sh that sleeps and fails).

        Call before start_daemon. A private LIB_DIR keeps HyDE's real pyutils.
        """
        real = Path(os.environ.get("LIB_DIR") or Path.home() / ".local" / "lib") / "hyde"
        lib = self.tmp / "lib" / "hyde"
        lib.mkdir(parents=True, exist_ok=True)
        (lib / "pyutils").symlink_to(real / "pyutils", target_is_directory=True)
        stub = lib / "wallbash.sh"
        stub.write_text(f"#!/bin/sh\nsleep {seconds}\nexit 1\n")
        stub.chmod(0o755)
        self.env["LIB_DIR"] = str(self.tmp / "lib")

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

    def set_rate(self, name: str, rate: float) -> None:
        """Set MPRIS Rate the way a player's speed control would (playerctl cannot)."""
        subprocess.run(
            [
                "gdbus",
                "call",
                "--session",
                "--dest",
                f"org.mpris.MediaPlayer2.{name}",
                "--object-path",
                "/org/mpris/MediaPlayer2",
                "--method",
                "org.freedesktop.DBus.Properties.Set",
                "org.mpris.MediaPlayer2.Player",
                "Rate",
                f"<{float(rate)}>",
            ],
            env=self.env,
            capture_output=True,
            check=True,
            timeout=5,
        )

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


def write_png(path: Path, size: int = 64, rgb: tuple[int, int, int] = (200, 40, 120)) -> Path:
    """A solid-color PNG cover, stdlib only."""
    import struct
    import zlib

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    row = b"\x00" + bytes(rgb) * size
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(row * size))
        + chunk(b"IEND", b"")
    )
    Path(path).write_bytes(png)
    return Path(path)


def thread_count(pid: int) -> int:
    for line in Path(f"/proc/{pid}/status").read_text().splitlines():
        if line.startswith("Threads:"):
            return int(line.split()[1])
    return 0
