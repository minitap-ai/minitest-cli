"""Helpers backing the ``user-story suggest-deps`` command.

Pulled out of ``user_story_suggest.py`` to keep both files under the
200-line cap (``tests/test_code_quality.py``) and mirror the existing
``<feature>_helpers.py`` pattern.
"""

from collections import defaultdict
from typing import Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.user_story_helpers import (
    base_path,
    handle_response_error,
    run_api_call,
)
from minitest_cli.models.user_story import (
    SuggestDependenciesResponse,
    SuggestedDependencyItem,
)
from minitest_cli.utils.output import output, print_warning


def emit_json(
    response: SuggestDependenciesResponse,
    settings: Any,
    app_id: str,
    *,
    yes: bool,
) -> None:
    """JSON-mode output: ``--yes`` applies immediately, otherwise raw dump."""
    payload: dict[str, Any] = {
        "suggestions": [s.model_dump(by_alias=True) for s in response.suggestions],
    }
    if yes:
        applied = apply_suggestions(settings, app_id, response.suggestions)
        payload["applied"] = [
            {"userStoryId": cid, "dependsOn": parents} for cid, parents in applied.items()
        ]
    output(payload, json_mode=True)


async def fetch_all_stories_inner(client: ApiClient, app_id: str) -> dict[str, dict[str, Any]]:
    """Page through ``/user-stories`` and return ``{id: story_dict}``."""
    out: dict[str, dict[str, Any]] = {}
    page = 1
    while True:
        resp = await client.get(base_path(app_id), params={"page": page, "page_size": 100})
        handle_response_error(resp)
        body = resp.json()
        items = body.get("items", []) if isinstance(body, dict) else body
        for item in items:
            sid = item.get("id")
            if sid:
                out[sid] = item
        total = body.get("total") if isinstance(body, dict) else None
        if not items or (total is not None and len(out) >= total):
            break
        page += 1
    return out


def apply_suggestions(
    settings: Any,
    app_id: str,
    accepted: list[SuggestedDependencyItem],
) -> dict[str, list[str]]:
    """Group accepted edges by child and PATCH each child once with the union
    of existing + new deps so webapp-wired deps survive."""
    by_child: dict[str, list[str]] = defaultdict(list)
    for s in accepted:
        by_child[s.user_story_id].append(s.depends_on_user_story_id)

    async def _run() -> dict[str, list[str]]:
        async with ApiClient(settings) as client:
            applied: dict[str, list[str]] = {}
            for child_id, new_parents in by_child.items():
                get_resp = await client.get(f"{base_path(app_id)}/{child_id}")
                handle_response_error(get_resp)
                current = get_resp.json()
                current_deps = current.get("dependsOn") or current.get("depends_on") or []
                merged = list({*current_deps, *new_parents})
                patch_resp = await client.patch(
                    f"{base_path(app_id)}/{child_id}",
                    json={"dependsOn": merged},
                )
                handle_response_error(patch_resp)
                applied[child_id] = merged
            return applied

    try:
        return run_api_call(_run())
    except typer.Exit:
        # A mid-batch 422 (e.g. cycle from a later suggestion) means earlier
        # PATCHes may have landed; warn so the user re-runs to see state.
        print_warning(
            "One or more PATCHes failed (likely a cycle introduced by the LLM "
            "suggestions). Earlier accepted suggestions may have been applied; "
            "re-run `user-story suggest-deps` to see the current state."
        )
        raise
