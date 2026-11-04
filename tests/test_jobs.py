import threading
import time

from encorelib.jobs import LatestJobs


def until(condition, timeout=2.0):
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "condition never held"
        time.sleep(0.005)


def blocking(gate, name, log, lock, live, peak):
    def job():
        with lock:
            log.append(name)
            live[0] += 1
            peak[0] = max(peak[0], live[0])
        gate.wait(2)
        with lock:
            live[0] -= 1

    return job


def test_runs_a_job():
    done = threading.Event()
    jobs = LatestJobs()
    jobs.submit(done.set)
    assert done.wait(2)
    assert jobs.join(2)


def test_queued_job_is_replaced():
    gate, lock, log, live, peak = threading.Event(), threading.Lock(), [], [0], [0]
    jobs = LatestJobs(workers=2)
    jobs.submit(blocking(gate, "busy1", log, lock, live, peak))
    until(lambda: len(log) == 1)  # back-to-back submits would replace busy1
    jobs.submit(blocking(gate, "busy2", log, lock, live, peak))
    until(lambda: len(log) == 2)
    jobs.submit(blocking(gate, "stale", log, lock, live, peak))
    jobs.submit(blocking(gate, "latest", log, lock, live, peak))
    gate.set()
    assert jobs.join(2)
    assert sorted(log) == ["busy1", "busy2", "latest"]


def test_never_exceeds_workers():
    gate, lock, log, live, peak = threading.Event(), threading.Lock(), [], [0], [0]
    jobs = LatestJobs(workers=2)
    for i in range(10):
        jobs.submit(blocking(gate, f"job{i}", log, lock, live, peak))
        if i < 2:
            until(lambda i=i: len(log) == i + 1)  # fill both workers first
    assert jobs.running() == 2
    gate.set()
    assert jobs.join(2)
    assert peak[0] <= 2
    assert log[-1] == "job9" and len(log) == 3


def test_job_exception_does_not_kill_worker():
    done = threading.Event()
    jobs = LatestJobs(workers=1)

    def boom():
        raise RuntimeError("provider blew up")

    jobs.submit(boom)
    assert jobs.join(2)
    jobs.submit(done.set)
    assert done.wait(2)
    assert jobs.join(2)
    assert jobs.running() == 0
