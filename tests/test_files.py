import errno

import pytest

from encorelib import files


def test_write_atomic_round_trip(tmp_path):
    target = tmp_path / "deep" / "state.txt"
    files.write_atomic(target, "hello\n")
    assert target.read_text() == "hello\n"
    assert [p.name for p in target.parent.iterdir()] == ["state.txt"]  # no tmp left


def test_write_atomic_cleans_its_tmp_when_the_disk_is_full(tmp_path, monkeypatch):
    target = tmp_path / "state.txt"
    target.write_text("old\n")

    def full(*_a, **_k):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(files.os, "replace", full)
    with pytest.raises(OSError):
        files.write_atomic(target, "new\n")
    assert target.read_text() == "old\n"  # the old file stands
    assert [p.name for p in tmp_path.iterdir()] == ["state.txt"]  # the tmp is gone


def test_copy_atomic_round_trip_and_cleanup(tmp_path, monkeypatch):
    src = tmp_path / "cover.png"
    src.write_bytes(b"\x89PNG fake")
    dst = tmp_path / "out" / "encore.cover.png"
    files.copy_atomic(src, dst)
    assert dst.read_bytes() == b"\x89PNG fake"
    assert [p.name for p in dst.parent.iterdir()] == ["encore.cover.png"]

    def full(*_a, **_k):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(files.shutil, "copyfile", full)
    with pytest.raises(OSError):
        files.copy_atomic(src, dst)
    assert [p.name for p in dst.parent.iterdir()] == ["encore.cover.png"]
