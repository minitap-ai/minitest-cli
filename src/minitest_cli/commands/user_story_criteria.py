"""Acceptance-criteria payload helpers for user-story update."""


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
