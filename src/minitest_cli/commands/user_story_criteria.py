"""Acceptance-criteria payload helpers for user-story update."""

from typing import Any

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.user_story_helpers import handle_response_error
from minitest_cli.commands.user_story_overrides import (
    ClearOverride,
    SetOverride,
    apply_override_edits,
)


def extract_criteria_items(story_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract existing criteria as wire-ready upsert items.

    The ``id`` uses the stable criterion identifier (``criterionId`` in the API
    response) so the backend preserves identity across updates; any existing
    ``platformOverrides`` are carried through so a content sync re-sends them.
    """
    raw = story_data.get("acceptanceCriteria") or story_data.get("acceptance_criteria") or []
    items: list[dict[str, Any]] = []
    for entry in raw:
        if isinstance(entry, dict):
            content = entry.get("content")
            if not content:
                continue
            stable_id = entry.get("criterionId") or entry.get("criterion_id")
            item: dict[str, Any] = {"content": content}
            if stable_id:
                item["id"] = stable_id
            overrides = entry.get("platformOverrides")
            if overrides is None:
                overrides = entry.get("platform_overrides")
            if overrides:
                item["platformOverrides"] = overrides
            items.append(item)
        elif entry:
            items.append({"content": str(entry)})
    return items


async def apply_current_story_fields(
    client: ApiClient,
    path: str,
    payload: dict[str, Any],
    *,
    criteria: list[str] | None,
    add_criteria: list[str] | None,
    remove_dependency: list[str] | None,
    subtract_deps: bool,
    set_overrides: list[SetOverride] | None = None,
    clear_overrides: list[ClearOverride] | None = None,
) -> None:
    """Fetch the current story and merge criteria/override/dependency edits into payload."""
    get_resp = await client.get(path)
    handle_response_error(get_resp)
    current_story = get_resp.json()
    existing_items = extract_criteria_items(current_story)
    if criteria is not None or add_criteria:
        items = build_criteria_payload(
            existing_items,
            replace=list(criteria) if criteria is not None else None,
            add=list(add_criteria) if add_criteria else None,
        )
    elif set_overrides or clear_overrides:
        items = existing_items
    else:
        items = None
    if items is not None and (set_overrides or clear_overrides):
        items = apply_override_edits(items, set_overrides or [], clear_overrides or [])
    if items is not None:
        payload["acceptanceCriteria"] = items
    if subtract_deps:
        current_deps = current_story.get("dependsOn") or current_story.get("depends_on") or []
        to_remove = set(remove_dependency or [])
        payload["dependsOn"] = [d for d in current_deps if d not in to_remove]


def build_criteria_payload(
    existing_items: list[dict[str, Any]],
    *,
    replace: list[str] | None,
    add: list[str] | None,
) -> list[dict[str, Any]]:
    """Build the acceptanceCriteria payload preserving stable criterion ids and overrides.

    - ``replace`` (``--criteria``): full replacement. Any entry whose content
      matches an existing criterion keeps its stable ``id`` and existing
      ``platformOverrides``. New contents are sent without ``id``.
    - ``add`` (``--add-criteria``): append. Existing items are passed through
      untouched (ids and overrides preserved); new contents appended without ``id``.
    """
    by_content: dict[str, list[dict[str, Any]]] = {}
    for item in existing_items:
        content = item.get("content")
        if content:
            by_content.setdefault(content, []).append(item)

    if replace is not None:
        out: list[dict[str, Any]] = []
        for content in replace:
            matches = by_content.get(content)
            match = matches.pop(0) if matches else None
            if match and match.get("id"):
                new_item: dict[str, Any] = {"id": match["id"], "content": content}
                if match.get("platformOverrides"):
                    new_item["platformOverrides"] = match["platformOverrides"]
                out.append(new_item)
            else:
                out.append({"content": content})
        return out

    appended = [{"content": c} for c in (add or [])]
    return existing_items + appended
