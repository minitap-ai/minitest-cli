"""Acceptance-criteria payload helpers for user-story update."""

from typing import Any

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.user_story_helpers import extract_criteria_items, handle_response_error


async def apply_current_story_fields(
    client: ApiClient,
    path: str,
    payload: dict[str, Any],
    *,
    criteria: list[str] | None,
    add_criteria: list[str] | None,
    remove_dependency: list[str] | None,
    subtract_deps: bool,
) -> None:
    """Fetch the current story and merge criteria/dependency edits into payload.

    Criteria edits preserve stable criterion ids and dependency removals subtract
    from the live set, so both need the server's current state before the PATCH.
    """
    get_resp = await client.get(path)
    handle_response_error(get_resp)
    current_story = get_resp.json()
    if criteria is not None or add_criteria:
        existing_items = extract_criteria_items(current_story)
        payload["acceptanceCriteria"] = build_criteria_payload(
            existing_items,
            replace=list(criteria) if criteria is not None else None,
            add=list(add_criteria) if add_criteria else None,
        )
    if subtract_deps:
        current_deps = current_story.get("dependsOn") or current_story.get("depends_on") or []
        to_remove = set(remove_dependency or [])
        payload["dependsOn"] = [d for d in current_deps if d not in to_remove]


def build_criteria_payload(
    existing_items: list[dict[str, str]],
    *,
    replace: list[str] | None,
    add: list[str] | None,
) -> list[dict[str, str]]:
    """Build the acceptanceCriteria payload preserving stable criterion ids.

    - ``replace`` (``--criteria``): full replacement. Any entry whose content
      matches an existing criterion keeps its stable ``id`` so the backend does
      not churn identity. New contents are sent without ``id``.
    - ``add`` (``--add-criteria``): append. Existing items are passed through
      untouched (ids preserved); new contents appended without ``id``.
    """
    by_content: dict[str, list[dict[str, str]]] = {}
    for item in existing_items:
        content = item.get("content")
        if content:
            by_content.setdefault(content, []).append(item)

    if replace is not None:
        out: list[dict[str, str]] = []
        for content in replace:
            matches = by_content.get(content)
            match = matches.pop(0) if matches else None
            if match and match.get("id"):
                out.append({"id": match["id"], "content": content})
            else:
                out.append({"content": content})
        return out

    appended = [{"content": c} for c in (add or [])]
    return existing_items + appended
