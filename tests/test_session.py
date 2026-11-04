from encorelib.session import Quiet


def test_quiet_logs_once_per_interval():
    q = Quiet(interval=60.0)
    assert q.should("disk", now=100.0) is True
    assert q.should("disk", now=130.0) is False  # same trouble, too soon
    assert q.should("other", now=130.0) is True  # a different trouble speaks
    assert q.should("disk", now=161.0) is True  # a minute later it speaks again
    q.clear("disk")
    assert q.should("disk", now=162.0) is True  # cleared: the next failure logs at once
