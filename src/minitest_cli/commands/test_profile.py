import sys
from typing import Annotated, Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands import test_profile_default, test_profile_list
from minitest_cli.commands.test_profile_helpers import (
    app_base_path,
    get_app_flag,
    get_settings,
    handle_profile_response,
    is_json_mode,
    run_api_call,
)
from minitest_cli.core.app_context import resolve_app_id
from minitest_cli.core.auth import require_auth
from minitest_cli.utils.output import output, print_error, print_success

app = typer.Typer(name="test-profile", help="Test-profile operations (app-scoped).")
test_profile_list.register(app)
test_profile_default.register(app)


def _read_password(password: str | None, password_stdin: bool) -> str | None:
    if password_stdin:
        if password is not None:
            print_error("Use either --password or --password-stdin, not both.")
            raise typer.Exit(code=1)
        return sys.stdin.read().rstrip("\r\n")
    return password


@app.command(name="create")
def create_profile(
    name: Annotated[str, typer.Option("--name", help="Profile name.")],
    username: Annotated[
        str | None,
        typer.Option(
            "--username",
            help="Account email. Use <prefix>@qa.minitap.ai for OTP personas (no password); "
            "the agent reads login codes from that inbox. Omit to auto-generate one.",
        ),
    ] = None,
    password: Annotated[
        str | None, typer.Option("--password", help="Account password (use stdin for security).")
    ] = None,
    password_stdin: Annotated[
        bool,
        typer.Option("--password-stdin", help="Read the password from stdin (no echo)."),
    ] = False,
    about: Annotated[
        str | None, typer.Option("--about", help="Free-text notes about the account.")
    ] = None,
) -> None:
    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)
    app_id = resolve_app_id(settings, get_app_flag())
    pwd = _read_password(password, password_stdin)

    body: dict[str, Any] = {"name": name}
    if username is not None:
        body["username"] = username
    if pwd is not None:
        body["password"] = pwd
    if about is not None:
        body["about"] = about

    async def _run() -> dict[str, Any]:
        async with ApiClient(settings) as client:
            resp = await client.post(app_base_path(app_id), json=body)
            handle_profile_response(resp)
            return resp.json()

    data = run_api_call(_run())
    if not json_mode:
        print_success(f"Test profile created: {data.get('id', '')}")
    output(data, json_mode=json_mode)


@app.command(name="get")
def get_profile(
    profile_id: Annotated[str, typer.Argument(help="Test profile ID.")],
) -> None:
    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)
    app_id = resolve_app_id(settings, get_app_flag())

    async def _run() -> dict[str, Any]:
        async with ApiClient(settings) as client:
            resp = await client.get(f"{app_base_path(app_id)}/{profile_id}")
            handle_profile_response(resp)
            return resp.json()

    output(run_api_call(_run()), json_mode=json_mode)


@app.command(name="update")
def update_profile(
    profile_id: Annotated[str, typer.Argument(help="Test profile ID.")],
    name: Annotated[str | None, typer.Option("--name", help="New profile name.")] = None,
    username: Annotated[str | None, typer.Option("--username", help="New username.")] = None,
    password: Annotated[
        str | None, typer.Option("--password", help="New password (overrides existing).")
    ] = None,
    password_stdin: Annotated[
        bool,
        typer.Option("--password-stdin", help="Read the new password from stdin."),
    ] = False,
    clear_password: Annotated[
        bool,
        typer.Option("--clear-password", help="Remove the stored password."),
    ] = False,
    about: Annotated[
        str | None, typer.Option("--about", help="New about text (pass '' to clear).")
    ] = None,
) -> None:
    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)
    app_id = resolve_app_id(settings, get_app_flag())

    pwd = _read_password(password, password_stdin)
    if pwd is not None and clear_password:
        print_error("Use either --password/--password-stdin or --clear-password, not both.")
        raise typer.Exit(code=1)

    body: dict[str, Any] = {}
    if name is not None:
        body["name"] = name
    if username is not None:
        body["username"] = username
    if pwd is not None:
        body["password"] = pwd
    elif clear_password:
        body["password"] = None
    if about is not None:
        body["about"] = about

    if not body:
        print_error("Provide at least one field to update.")
        raise typer.Exit(code=1)

    async def _run() -> dict[str, Any]:
        async with ApiClient(settings) as client:
            resp = await client.patch(f"{app_base_path(app_id)}/{profile_id}", json=body)
            handle_profile_response(resp)
            return resp.json()

    data = run_api_call(_run())
    if not json_mode:
        print_success(f"Test profile updated: {profile_id}")
    output(data, json_mode=json_mode)


@app.command(name="delete")
def delete_profile(
    profile_id: Annotated[str, typer.Argument(help="Test profile ID.")],
    force: Annotated[bool, typer.Option("--force", help="Skip confirmation.")] = False,
) -> None:
    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)
    if not force:
        print_error("Delete requires --force flag.")
        raise typer.Exit(code=1)
    app_id = resolve_app_id(settings, get_app_flag())

    async def _run() -> None:
        async with ApiClient(settings) as client:
            resp = await client.delete(f"{app_base_path(app_id)}/{profile_id}")
            handle_profile_response(resp)

    run_api_call(_run())
    if json_mode:
        output({"deleted": True, "id": profile_id}, json_mode=True)
    else:
        print_success(f"Test profile deleted: {profile_id}")
