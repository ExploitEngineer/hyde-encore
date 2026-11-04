import pytest
from harness import Harness, missing_requirement

_MISSING = missing_requirement()


@pytest.fixture
def harness(tmp_path):
    """A private bus, runtime dir and fake players; see harness.py."""
    if _MISSING:
        pytest.skip(f"e2e harness unavailable: {_MISSING}")
    with Harness(tmp_path) as h:
        yield h
