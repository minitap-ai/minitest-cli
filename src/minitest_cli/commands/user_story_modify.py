"""User-story modification commands: update, delete."""

from typing import Annotated, Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.user_story_helpers import (
    base_path,
    extract_criteria_items,
    get_app_flag,
    get_settings,
    handle_response_error,
    is_json_mode,
    run_api_call,
    validate_user_story_type,
)
from minitest_cli.core.app_context import resolve_app_id
from minitest_cli.core.auth import require_auth
from minitest_cli.models.user_story import UpdateUserStoryRequest
from minitest_cli.utils.output import output, print_error, print_success, print_warning


def _build_criteria_payload(
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


def update_user_story(
    user_story_id: Annotated[str, typer.Argument(help="User-story ID.")],
    name: Annotated[str | None, typer.Option("--name", help="New user-story name.")] = None,
    user_story_type: Annotated[
        str | None, typer.Option("--type", help="New user-story type.")
    ] = None,
    description: Annotated[
        str | None, typer.Option("--description", help="New description.")
    ] = None,
    criteria: Annotated[
        list[str] | None,
        typer.Option("--criteria", help="Replace acceptance criteria (repeatable)."),
    ] = None,
    add_criteria: Annotated[
        list[str] | None,
        typer.Option("--add-criteria", help="Append acceptance criteria (repeatable)."),
    ] = None,
    depends_on: Annotated[
        list[str] | None,
        typer.Option(
            "--depends-on",
            help=(
                "Replace the full set of parent user-story IDs (repeatable). "
                "Pass each parent ID once. Validated server-side: same-app, "
                "no cycles, no self-loops, references must exist."
            ),
        ),
    ] = None,
    remove_dependency: Annotated[
        list[str] | None,
        typer.Option(
            "--remove-dependency",
            help=(
                "Remove specific parent user-story IDs from the existing set "
                "(repeatable). Ignored when --depends-on is also provided."
            ),
        ),
    ] = None,
) -> None:
    """Update an existing user story (partial update).

    When you already know which flows gate this one, prefer ``--depends-on``
    over the ``suggest-deps`` command — it's deterministic and free.
    """
    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)
    app_id = resolve_app_id(settings, get_app_flag())

    if criteria is not None and add_criteria is not None:
        print_error("Use either --criteria or --add-criteria, not both.")
        raise typer.Exit(code=1)

    if user_story_type is not None:
        validate_user_story_type(user_story_type, settings)

    # ``--depends-on`` is the replace path; ``--remove-dependency`` is a delta
    # against the current set. If both are given, the spec says replace wins —
    # warn loudly so the user notices the surgical removal was dropped.
    if depends_on is not None and remove_dependency:
        print_warning("--remove-dependency ignored when --depends-on is set.")

    # When --criteria (full replace), --add-criteria (append), or
    # --remove-dependency (delta against the current set) is used we need the
    # current story so we can either preserve stable criterion identity or
    # subtract from the live dep set. We defer building the final payload
    # until after that GET.
    needs_current_story_criteria = criteria is not None or bool(add_criteria)
    needs_current_story_deps = depends_on is None and bool(remove_dependency)
    needs_current_story = needs_current_story_criteria or needs_current_story_deps

    req = UpdateUserStoryRequest(
        name=name,
        type=user_story_type,
        description=description,
        acceptance_criteria=None,
        depends_on=list(depends_on) if depends_on is not None else None,
    )
    if not req.has_changes() and not needs_current_story:
        print_error("Provide at least one field to update.")
        raise typer.Exit(code=1)

    payload = req.to_payload()

    async def _run() -> dict[str, Any]:
        async with ApiClient(settings) as client:
            path = f"{base_path(app_id)}/{user_story_id}"
            if needs_current_story:
                get_resp = await client.get(path)
                handle_response_error(get_resp)
                current_story = get_resp.json()
                if needs_current_story_criteria:
                    existing_items = extract_criteria_items(current_story)
                    payload["acceptanceCriteria"] = _build_criteria_payload(
                        existing_items,
                        replace=list(criteria) if criteria is not None else None,
                        add=list(add_criteria) if add_criteria else None,
                    )
                if needs_current_story_deps:
                    current_deps = (
                        current_story.get("dependsOn") or current_story.get("depends_on") or []
                    )
                    to_remove = set(remove_dependency or [])
                    payload["dependsOn"] = [d for d in current_deps if d not in to_remove]
            resp = await client.patch(path, json=payload)
            handle_response_error(resp)
            return resp.json()

    data = run_api_call(_run())
    if not json_mode:
        print_success(f"User story updated: {user_story_id}")
    output(data, json_mode=json_mode)


def delete_user_story(
    user_story_id: Annotated[str, typer.Argument(help="User-story ID.")],
    force: Annotated[bool, typer.Option("--force", help="Skip confirmation.")] = False,
) -> None:
    """Delete a user story. Requires --force flag."""
    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)
    if not force:
        print_error("Delete requires --force flag.")
        raise typer.Exit(code=1)
    app_id = resolve_app_id(settings, get_app_flag())

    async def _run() -> None:
        async with ApiClient(settings) as client:
            resp = await client.delete(f"{base_path(app_id)}/{user_story_id}")
            handle_response_error(resp)

    run_api_call(_run())
    if json_mode:
        output({"deleted": True, "id": user_story_id}, json_mode=True)
    else:
        print_success(f"User story deleted: {user_story_id}")
