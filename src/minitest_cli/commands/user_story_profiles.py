"""Helpers for extracting and rendering test profiles from user-story responses."""

from typing import Any


def extract_bound_profiles(story_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the test profiles bound to a story as ``{id, name, ...}`` dicts.

    Prefers the plural ``testProfiles`` list and falls back to the legacy
    singular ``testProfile``/``testProfileId`` fields so the CLI keeps working
    against servers that have not shipped the multi-profile response yet.
    """
    plural = story_data.get("testProfiles") or story_data.get("test_profiles")
    if plural:
        return [p for p in plural if isinstance(p, dict)]
    singular = story_data.get("testProfile") or story_data.get("test_profile")
    if isinstance(singular, dict):
        return [singular]
    profile_id = story_data.get("testProfileId") or story_data.get("test_profile_id")
    if profile_id:
        return [{"id": profile_id}]
    return []


def format_bound_profiles(story_data: dict[str, Any]) -> str:
    """Render bound profiles as a compact ``name`` list for table cells."""
    profiles = extract_bound_profiles(story_data)
    labels = [str(p.get("name") or p.get("id") or "") for p in profiles]
    return ", ".join(label for label in labels if label)
