"""Scenario commands (legacy name: user story): list, get."""

from typing import Annotated, Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands import (
    user_story_create,
    user_story_delete,
    user_story_modify,
    user_story_setup_commit,
)
from minitest_cli.commands.deprecated_alias import deprecated_alias
from minitest_cli.commands.tags_helpers import (
    LegacyTypeOption,
    collect_tag_names,
    resolve_tag_ids,
)
from minitest_cli.commands.user_story_device_count import effective_device_count
from minitest_cli.commands.user_story_helpers import (
    USER_STORY_TABLE_HEADERS,
    base_path,
    fetch_all_user_stories,
    format_pagination_info,
    format_user_story_row,
    get_app_flag,
    get_settings,
    handle_response_error,
    is_json_mode,
    page_items,
    run_api_call,
)
from minitest_cli.commands.user_story_profiles import format_bound_profiles
from minitest_cli.core.app_context import resolve_app_id
from minitest_cli.core.auth import require_auth
from minitest_cli.utils.output import output, print_info, print_table

app = typer.Typer(name="scenario", help="Create, update, list and delete scenarios.")
app.command(name="create")(user_story_create.create_user_story)
app.command(name="update")(user_story_modify.update_user_story)
app.command(name="delete")(user_story_delete.delete_user_story)
app.command(name="allow-setup-commit")(user_story_setup_commit.allow_setup_commit)
app.command(name="revoke-setup-commit")(user_story_setup_commit.revoke_setup_commit)


@app.command(name="list")
def list_user_stories(
    tag: Annotated[
        list[str] | None,
        typer.Option("--tag", help="Only scenarios carrying any of these tags (repeatable)."),
    ] = None,
    user_story_type: LegacyTypeOption = None,
    page: Annotated[int, typer.Option("--page", min=1, help="Page number.")] = 1,
    page_size: Annotated[
        int, typer.Option("--page-size", min=1, max=100, help="Items per page.")
    ] = 20,
    all_stories: Annotated[
        bool,
        typer.Option("--all", help="Fetch all scenarios (ignores --page and --page-size)."),
    ] = False,
) -> None:
    """List scenarios for the active app."""
    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)
    app_id = resolve_app_id(settings, get_app_flag())
    tag_names = collect_tag_names(tag, user_story_type)

    async def _run() -> Any:
        async with ApiClient(settings) as client:
            params: dict[str, Any] = {}
            if tag_names:
                params["tagId"] = await resolve_tag_ids(client, app_id, tag_names)
            if all_stories:
                return await fetch_all_user_stories(client, app_id, params)
            resp = await client.get(
                base_path(app_id), params={**params, "page": page, "page_size": page_size}
            )
            handle_response_error(resp)
            return resp.json()

    data = run_api_call(_run())
    if json_mode:
        output(data, json_mode=True)
        return

    items = page_items(data)
    if not items:
        print_info("No scenarios found.")
        return

    if all_stories:
        title = f"Scenarios (showing all {len(items)} scenarios)"
        tip = None
    elif isinstance(data, dict):
        title, tip = format_pagination_info(data, page, page_size)
    else:
        title, tip = "Scenarios", None
    show_devices = any(effective_device_count(s) > 1 for s in items)
    headers = [*USER_STORY_TABLE_HEADERS, "Devices"] if show_devices else USER_STORY_TABLE_HEADERS
    rows = [format_user_story_row(s, show_devices=show_devices) for s in items]
    print_table(headers, rows, title=title)
    if tip:
        print_info(tip)


@app.command(name="get")
def get_user_story(
    user_story_id: Annotated[str, typer.Argument(help="Scenario ID.")],
) -> None:
    """Show details for a specific scenario."""
    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)
    app_id = resolve_app_id(settings, get_app_flag())

    async def _run() -> dict[str, Any]:
        async with ApiClient(settings) as client:
            resp = await client.get(f"{base_path(app_id)}/{user_story_id}")
            handle_response_error(resp)
            return resp.json()

    data = run_api_call(_run())
    if not json_mode:
        print_info(f"Bound profiles: {format_bound_profiles(data) or 'none'}")
        effective = effective_device_count(data)
        if effective > 1:
            print_info(f"Devices per run: {effective}")
        permission = data.get("setupCommitPermission")
        if isinstance(permission, dict):
            print_info(f"Setup commit allowed: {permission.get('customerQuote')}")
    output(data, json_mode=json_mode)


legacy_app = deprecated_alias(app, old_name="user-story")
