"""User-story delete command."""

from typing import Annotated

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.user_story_helpers import (
    base_path,
    get_app_flag,
    get_settings,
    handle_response_error,
    is_json_mode,
    run_api_call,
)
from minitest_cli.core.app_context import resolve_app_id
from minitest_cli.core.auth import require_auth
from minitest_cli.utils.output import output, print_error, print_success


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
