"""Paths shared by the unit tests (a plain module: tests/e2e has its own conftest)."""

from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"
