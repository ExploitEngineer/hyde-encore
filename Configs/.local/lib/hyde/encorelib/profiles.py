"""Sound-setup profiles: a quiet set for working. Full screen replaced the show."""

from __future__ import annotations

from pathlib import Path

from .look import update_look

PROFILES: dict[str, dict] = {
    "working": {
        "glow": False,
        "look": {"style": "line", "motion": False, "size": None, "next_line": True},
    },
}


def apply_profile(look_path: Path, name: str, persist: Path | None = None) -> bool | None:
    """Write the profile's look keys; returns the wanted glow state."""
    profile = PROFILES.get(name)
    if profile is None:
        return None
    update_look(look_path, persist=persist, **profile["look"])
    return profile["glow"]
