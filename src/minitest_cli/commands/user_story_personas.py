from typing import Any


def format_bound_personas(story_data: dict[str, Any]) -> str:
    """The personas a scenario plays, by name, for table cells and summaries."""
    personas = story_data.get("personas") or []
    return ", ".join(str(p.get("name") or p.get("id")) for p in personas if isinstance(p, dict))
