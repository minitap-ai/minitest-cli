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
from minitest_cli.models.user_story import CriterionUpsertItem, UpdateUserStoryRequest
from minitest_cli.utils.output import output, print_error, print_success


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
) -> None:
    """Update an existing user story (partial update)."""
    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)
    app_id = resolve_app_id(settings, get_app_flag())

    if criteria is not None and add_criteria is not None:
        print_error("Use either --criteria or --add-criteria, not both.")
        raise typer.Exit(code=1)

    if user_story_type is not None:
        validate_user_story_type(user_story_type, settings)

    criteria_items: list[CriterionUpsertItem] | None = (
        [CriterionUpsertItem(content=c) for c in criteria] if criteria is not None else None
    )
    req = UpdateUserStoryRequest(
        name=name,
        type=user_story_type,
        description=description,
        acceptance_criteria=criteria_items,
    )
    if not req.has_changes() and not add_criteria:
        print_error("Provide at least one field to update.")
        raise typer.Exit(code=1)

    payload = req.to_payload()

    async def _run() -> dict[str, Any]:
        async with ApiClient(settings) as client:
            path = f"{base_path(app_id)}/{user_story_id}"
            if add_criteria:
                get_resp = await client.get(path)
                handle_response_error(get_resp)
                existing_items = extract_criteria_items(get_resp.json())
                new_items = [{"content": c} for c in add_criteria]
                payload["acceptanceCriteria"] = existing_items + new_items
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
