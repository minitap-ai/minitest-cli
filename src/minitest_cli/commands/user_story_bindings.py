from typing import Annotated, Any

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
from minitest_cli.utils.output import output, print_error, print_info, print_success, print_table

app = typer.Typer(name="user-story-binding", help="Bind test profiles or files to user stories.")

_FILE_BINDING_HEADERS = ["ID", "Name", "Kind"]


def _binding_row(entry: dict[str, Any]) -> list[str]:
    return [str(entry.get("id", "")), entry.get("name", ""), entry.get("kind", "") or ""]


def _normalize_items(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        return data.get("items", [])
    if isinstance(data, list):
        return data
    return []


@app.command(name="set-profile")
def set_profile(
    user_story_id: Annotated[str, typer.Argument(help="User-story ID.")],
    profile_id: Annotated[
        str | None,
        typer.Option("--profile", help="Test profile ID to bind. Omit with --clear to remove."),
    ] = None,
    clear: Annotated[
        bool,
        typer.Option("--clear", help="Remove the existing profile binding."),
    ] = False,
) -> None:
    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)
    app_id = resolve_app_id(settings, get_app_flag())

    if profile_id is not None and clear:
        print_error("Use either --profile or --clear, not both.")
        raise typer.Exit(code=1)
    if profile_id is None and not clear:
        print_error("Provide --profile <id> or --clear.")
        raise typer.Exit(code=1)

    body: dict[str, Any] = {"testProfileId": None if clear else profile_id}

    async def _run() -> dict[str, Any]:
        async with ApiClient(settings) as client:
            resp = await client.patch(f"{base_path(app_id)}/{user_story_id}", json=body)
            handle_response_error(resp)
            return resp.json()

    data = run_api_call(_run())
    if not json_mode:
        if clear:
            print_success(f"Test profile cleared on user story {user_story_id}.")
        else:
            print_success(f"Test profile {profile_id} bound to user story {user_story_id}.")
    output(data, json_mode=json_mode)


@app.command(name="set-files")
def set_files(
    user_story_id: Annotated[str, typer.Argument(help="User-story ID.")],
    file_ids: Annotated[
        list[str] | None,
        typer.Option(
            "--file",
            help="Test file ID to bind (repeatable). Pass none + --clear to unbind all.",
        ),
    ] = None,
    clear: Annotated[
        bool, typer.Option("--clear", help="Atomically clear all file bindings.")
    ] = False,
) -> None:
    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)
    app_id = resolve_app_id(settings, get_app_flag())

    if clear and file_ids:
        print_error("Use either --file or --clear, not both.")
        raise typer.Exit(code=1)
    if not clear and not file_ids:
        print_error("Provide at least one --file <id> or --clear.")
        raise typer.Exit(code=1)

    body = {"fileIds": [] if clear else list(file_ids or [])}

    async def _run() -> dict[str, Any]:
        async with ApiClient(settings) as client:
            resp = await client.put(
                f"{base_path(app_id)}/{user_story_id}/files",
                json=body,
            )
            handle_response_error(resp)
            return resp.json()

    data = run_api_call(_run())
    items = _normalize_items(data)
    if json_mode:
        output(data, json_mode=True)
        return
    if not items:
        print_info("No files bound to this user story.")
        return
    rows = [_binding_row(f) for f in items]
    print_table(_FILE_BINDING_HEADERS, rows, title=f"Files bound to {user_story_id} ({len(items)})")


@app.command(name="list-files")
def list_files(
    user_story_id: Annotated[str, typer.Argument(help="User-story ID.")],
    page: Annotated[int, typer.Option("--page", min=1)] = 1,
    page_size: Annotated[int, typer.Option("--page-size", min=1, max=100)] = 50,
) -> None:
    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)
    app_id = resolve_app_id(settings, get_app_flag())

    async def _run() -> dict[str, Any]:
        async with ApiClient(settings) as client:
            resp = await client.get(
                f"{base_path(app_id)}/{user_story_id}/files",
                params={"page": page, "pageSize": page_size},
            )
            handle_response_error(resp)
            return resp.json()

    data = run_api_call(_run())
    items = _normalize_items(data)
    if json_mode:
        output(data, json_mode=True)
        return
    if not items:
        print_info("No files bound to this user story.")
        return
    rows = [_binding_row(f) for f in items]
    print_table(_FILE_BINDING_HEADERS, rows, title=f"Files bound to {user_story_id} ({len(items)})")
