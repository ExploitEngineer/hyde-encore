import json

from encorelib.journal import append_capped, read_lines


def test_append_keeps_the_newest(tmp_path):
    path = tmp_path / "encore.lookups"
    for i in range(60):
        append_capped(path, {"i": i}, keep=50)
    rows = read_lines(path)
    assert [r["i"] for r in rows] == list(range(10, 60))


def test_read_skips_damaged_lines(tmp_path):
    path = tmp_path / "encore.lookups"
    path.write_text('{"i": 1}\nnot json\n{"i": 2}\n', encoding="utf-8")
    assert read_lines(path) == [{"i": 1}, {"i": 2}]
    assert read_lines(tmp_path / "missing") == []


def test_append_writes_unicode_as_is(tmp_path):
    path = tmp_path / "encore.lookups"
    append_capped(path, {"title": "夜に駆ける"})
    assert "夜に駆ける" in path.read_text(encoding="utf-8")
    assert json.loads(path.read_text(encoding="utf-8").strip())["title"] == "夜に駆ける"


def test_append_never_raises(tmp_path):
    ro = tmp_path / "ro"
    ro.mkdir()
    ro.chmod(0o500)
    try:
        append_capped(ro / "sub" / "encore.lookups", {"i": 1})  # mkdir fails
        append_capped(ro / "encore.lookups", {"i": 1})  # mkstemp fails
    finally:
        ro.chmod(0o700)


def test_concurrent_appends_keep_every_record(tmp_path):
    import threading

    path = tmp_path / "encore.lookups"

    def worker(n):
        for i in range(20):
            append_capped(path, {"w": n, "i": i}, keep=100)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(read_lines(path)) == 40
