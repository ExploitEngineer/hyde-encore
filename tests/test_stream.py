from encorelib.stream import LineDecoder, should_connect


def test_split_across_chunks():
    d = LineDecoder()
    assert d.feed(b'{"a": ') == []
    assert d.feed(b"1}\n") == [{"a": 1}]


def test_multiple_lines_in_one_chunk():
    assert LineDecoder().feed(b'{"a":1}\n{"b":2}\n') == [{"a": 1}, {"b": 2}]


def test_invalid_json_skipped():
    assert LineDecoder().feed(b'not json\n{"ok":true}\n') == [{"ok": True}]


def test_non_object_skipped():
    assert LineDecoder().feed(b'[1,2]\n42\n"str"\n{"ok":1}\n') == [{"ok": 1}]


def test_oversized_tail_dropped():
    d = LineDecoder()
    assert d.feed(b"x" * (1024 * 1024 + 1)) == []
    assert d.feed(b'{"fresh":1}\n') == [{"fresh": 1}]


def test_reset_clears_partial():
    d = LineDecoder()
    d.feed(b'{"half":')
    d.reset()
    assert d.feed(b'{"whole":1}\n') == [{"whole": 1}]


def test_should_connect_on_socket_only():
    assert should_connect("/run/user/1000/hyde/encore.sock") is True
    assert should_connect("/run/user/1000/hyde/encore.hyprlock") is False
    assert should_connect("/run/user/1000/hyde/cava.sock") is False
