"""Sound-setup profiles: one quiet set for working, one for the full show."""

from __future__ import annotations

from pathlib import Path

from .look import update_look

PROFILES: dict[str, dict] = {
    "working": {
        "glow": False,
        "look": {"style": "line", "motion": False, "size": None, "next_line": True},
    },
    "show": {
        "glow": True,
        "look": {"style": "visual", "motion": True, "size": 40, "next_line": False},
    },
}


def apply_profile(look_path: Path, name: str, persist: Path | None = None) -> bool | None:
    """Write the profile's look keys; returns the wanted glow state."""
    profile = PROFILES.get(name)
    if profile is None:
        return None
    update_look(look_path, persist=persist, **profile["look"])
    return profile["glow"]


SHOW_WORKSPACE = "encore"


def show_action(active_workspace_name: str) -> str:
    """Toggle semantics of `encore show`: enter the show workspace, or leave it."""
    return "leave" if active_workspace_name == SHOW_WORKSPACE else "enter"
