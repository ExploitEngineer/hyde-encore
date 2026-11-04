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
