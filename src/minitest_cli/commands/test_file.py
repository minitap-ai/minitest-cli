"""Test-file commands: upload, get, update, delete (list in test_file_list)."""

import mimetypes
from pathlib import Path
from typing import Annotated, Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands import test_file_list
from minitest_cli.commands.test_file_helpers import (
    MAX_UPLOAD_BYTES,
    base_path,
    get_app_flag,
    get_settings,
    handle_file_response,
    is_json_mode,
    run_api_call,
)
from minitest_cli.core.app_context import resolve_app_id
from minitest_cli.core.auth import require_auth
from minitest_cli.utils.output import output, print_error, print_success

app = typer.Typer(name="test-file", help="Test-file operations (app-scoped).")
test_file_list.register(app)


@app.command(name="upload")
def upload_file(
    path: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
            help="Path to the local file to upload.",
        ),
    ],
    name: Annotated[
        str | None, typer.Option("--name", help="Display name (defaults to the file basename).")
    ] = None,
    note: Annotated[
        str | None, typer.Option("--note", help="Optional 'what this file is for' note.")
    ] = None,
) -> None:
    """Upload a test file (multipart, max 25 MB)."""
    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)
    app_id = resolve_app_id(settings, get_app_flag())

    size = path.stat().st_size
    if size > MAX_UPLOAD_BYTES:
        print_error(f"File too large: {size} bytes (max {MAX_UPLOAD_BYTES} bytes / 25 MB).")
        raise typer.Exit(code=1)

    mime, _ = mimetypes.guess_type(path.name)
    mime = mime or "application/octet-stream"

    async def _run() -> dict[str, Any]:
        async with ApiClient(settings) as client:
            with path.open("rb") as fh:
                data = {}
                if name is not None:
                    data["name"] = name
                if note is not None:
                    data["note"] = note
                resp = await client.upload_file(
                    base_path(app_id),
                    files={"file": (path.name, fh, mime)},
                    data=data,
                )
            handle_file_response(resp)
            return resp.json()

    data = run_api_call(_run())
    if not json_mode:
        print_success(f"Test file uploaded: {data.get('id', '')}")
    output(data, json_mode=json_mode)


@app.command(name="get")
def get_file(
    file_id: Annotated[str, typer.Argument(help="Test file ID.")],
) -> None:
    """Get a test file's metadata with a short-lived download URL."""
    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)
    app_id = resolve_app_id(settings, get_app_flag())

    async def _run() -> dict[str, Any]:
        async with ApiClient(settings) as client:
            resp = await client.get(f"{base_path(app_id)}/{file_id}")
            handle_file_response(resp)
            return resp.json()

    output(run_api_call(_run()), json_mode=json_mode)


@app.command(name="update")
def update_file(
    file_id: Annotated[str, typer.Argument(help="Test file ID.")],
    name: Annotated[str | None, typer.Option("--name", help="New display name.")] = None,
    note: Annotated[str | None, typer.Option("--note", help="New note.")] = None,
    clear_note: Annotated[
        bool, typer.Option("--clear-note", help="Remove the existing note.")
    ] = False,
) -> None:
    """Update a test file's metadata (partial)."""
    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)
    app_id = resolve_app_id(settings, get_app_flag())

    if note is not None and clear_note:
        print_error("Use either --note or --clear-note, not both.")
        raise typer.Exit(code=1)

    body: dict[str, Any] = {}
    if name is not None:
        body["name"] = name
    if note is not None:
        body["note"] = note
    if clear_note:
        body["clearNote"] = True

    if not body:
        print_error("Provide at least one field to update.")
        raise typer.Exit(code=1)

    async def _run() -> dict[str, Any]:
        async with ApiClient(settings) as client:
            resp = await client.patch(f"{base_path(app_id)}/{file_id}", json=body)
            handle_file_response(resp)
            return resp.json()

    data = run_api_call(_run())
    if not json_mode:
        print_success(f"Test file updated: {file_id}")
    output(data, json_mode=json_mode)


@app.command(name="delete")
def delete_file(
    file_id: Annotated[str, typer.Argument(help="Test file ID.")],
    force: Annotated[bool, typer.Option("--force", help="Skip confirmation.")] = False,
) -> None:
    """Delete a test file. Requires --force."""
    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)
    if not force:
        print_error("Delete requires --force flag.")
        raise typer.Exit(code=1)
    app_id = resolve_app_id(settings, get_app_flag())

    async def _run() -> None:
        async with ApiClient(settings) as client:
            resp = await client.delete(f"{base_path(app_id)}/{file_id}")
            handle_file_response(resp)

    run_api_call(_run())
    if json_mode:
        output({"deleted": True, "id": file_id}, json_mode=True)
    else:
        print_success(f"Test file deleted: {file_id}")
