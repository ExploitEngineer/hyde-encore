import socket

from encorelib.service import daemon_alive, daemon_start_command, daemon_unit, ensure_daemon


def test_daemon_unit_matches_hyde_autostart_name():
    assert daemon_unit("Hyprland") == "hyde-Hyprland-encore.service"
    assert daemon_unit("") == "hyde-Hyprland-encore.service"


def test_daemon_start_command_runs_through_hyde_shell_app():
    assert daemon_start_command("Hyprland") == [
        "hyde-shell",
        "app",
        "-u",
        "hyde-Hyprland-encore.service",
        "-t",
        "service",
        "--",
        "encore.sh",
        "daemon",
    ]


def test_daemon_alive_false_without_socket(tmp_path):
    assert daemon_alive(tmp_path / "encore.sock") is False


def test_daemon_alive_false_for_stale_socket_file(tmp_path):
    path = tmp_path / "encore.sock"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    server.close()  # the file stays, nobody listens: a crashed daemon
    assert daemon_alive(path) is False


def test_daemon_alive_true_with_listener(tmp_path):
    path = tmp_path / "encore.sock"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    server.listen(1)
    try:
        assert daemon_alive(path) is True
    finally:
        server.close()


class Runner:
    def __init__(self, returncode=0, error=None):
        self.returncode, self.error, self.calls = returncode, error, []

    def __call__(self, command, **kw):
        self.calls.append(command)
        if self.error:
            raise self.error

        class Result:
            returncode = self.returncode

        return Result()


def test_ensure_daemon_leaves_a_running_daemon_alone(tmp_path):
    path = tmp_path / "encore.sock"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    server.listen(1)
    run, spawned = Runner(), []
    try:
        assert ensure_daemon(path, "Hyprland", run, lambda: spawned.append(1)) == "running"
    finally:
        server.close()
    assert run.calls == [] and spawned == []


def test_ensure_daemon_starts_the_hyde_unit(tmp_path):
    run, spawned = Runner(), []
    state = ensure_daemon(tmp_path / "encore.sock", "Hyprland", run, lambda: spawned.append(1))
    assert state == "started"
    assert run.calls[-1] == daemon_start_command("Hyprland")
    assert spawned == []


def test_ensure_daemon_falls_back_when_the_unit_fails(tmp_path):
    spawned = []
    state = ensure_daemon(tmp_path / "s", "Hyprland", Runner(1), lambda: spawned.append(1))
    assert state == "fallback" and spawned == [1]


def test_ensure_daemon_falls_back_without_hyde_shell(tmp_path):
    spawned = []
    run = Runner(error=FileNotFoundError("hyde-shell"))
    assert ensure_daemon(tmp_path / "s", "", run, lambda: spawned.append(1)) == "fallback"
    assert spawned == [1]


class RecordingRunner(Runner):
    def __call__(self, command, **kw):
        self.kwargs = getattr(self, "kwargs", []) + [kw]
        return super().__call__(command, **kw)


def test_ensure_daemon_starts_from_home_and_clears_a_failed_unit(tmp_path):
    from pathlib import Path

    run = RecordingRunner()
    assert ensure_daemon(tmp_path / "s", "Hyprland", run, lambda: None) == "started"
    assert run.calls == [
        ["systemctl", "--user", "reset-failed", "hyde-Hyprland-encore.service"],
        daemon_start_command("Hyprland"),
    ]
    # app2unit starts units with --same-dir: a cwd that later vanishes breaks restarts
    assert all(kw.get("cwd") == Path.home() for kw in run.kwargs)


def test_ensure_daemon_never_touches_units_in_tests(tmp_path):
    calls, fell_back = [], []

    def run(cmd, **_kw):
        calls.append(cmd)
        raise AssertionError("a unit command ran")

    result = ensure_daemon(
        tmp_path / "encore.sock",
        "Hyprland",
        run=run,
        fallback=lambda: fell_back.append(True),
        env={"ENCORE_NO_UNIT": "1"},
    )
    assert result == "fallback"
    assert calls == [] and fell_back == [True]
