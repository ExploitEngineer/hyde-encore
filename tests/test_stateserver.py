"""The state socket under pressure: pollers come and go, descriptors run out."""

import errno
import socket

from encorelib.protocol import StateServer


def _poller(path):
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(1.0)
    client.connect(str(path))
    return client


def test_accept_makes_room_when_out_of_descriptors(tmp_path, monkeypatch):
    server = StateServer(tmp_path / "encore.sock")
    server.start()
    pollers = []
    try:
        server.broadcast({"v": 1})
        for _ in range(2):  # two pollers connected and still reading
            pollers.append(_poller(server.path))
            server.accept()
        assert len(server.clients) == 2
        oldest, newest = server.clients

        def out_of_fds():
            raise OSError(errno.EMFILE, "Too many open files")

        monkeypatch.setattr(server, "_accept_one", out_of_fds)
        server.accept()  # must not raise: the oldest poller makes room, the listener lives
        assert server.clients == [newest]
        assert oldest.fileno() == -1
    finally:
        for p in pollers:
            p.close()
        server.close()


def test_accept_ignores_a_connection_that_went_away(tmp_path, monkeypatch):
    server = StateServer(tmp_path / "encore.sock")
    server.start()
    try:

        def aborted():
            raise OSError(errno.ECONNABORTED, "Software caused connection abort")

        monkeypatch.setattr(server, "_accept_one", aborted)
        server.accept()
        assert server.clients == []
    finally:
        server.close()
