from typing import Annotated, Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands import test_profile_default, test_profile_list, test_profile_update
from minitest_cli.commands.test_profile_helpers import (
    app_base_path,
    get_app_flag,
    get_settings,
    handle_profile_response,
    is_json_mode,
    read_stdin_secret,
    run_api_call,
)
from minitest_cli.core.app_context import resolve_app_id
from minitest_cli.core.auth import require_auth
from minitest_cli.utils.output import output, print_error, print_success

app = typer.Typer(name="test-profile", help="Test-profile operations (app-scoped).")
test_profile_list.register(app)
test_profile_default.register(app)
test_profile_update.register(app)


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
    phone_number: Annotated[
        str | None,
        typer.Option(
            "--phone-number",
            help="E.164 phone number whitelisted in the customer's backend, for phone-OTP "
            "personas (e.g. +14155551234).",
        ),
    ] = None,
    static_otp_code: Annotated[
        str | None,
        typer.Option(
            "--static-otp-code",
            help="Fixed OTP code the customer's backend accepts (use stdin for security).",
        ),
    ] = None,
    static_otp_code_stdin: Annotated[
        bool,
        typer.Option(
            "--static-otp-code-stdin", help="Read the static OTP code from stdin (no echo)."
        ),
    ] = False,
    about: Annotated[
        str | None, typer.Option("--about", help="Free-text notes about the account.")
    ] = None,
) -> None:
    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)
    app_id = resolve_app_id(settings, get_app_flag())
    pwd = read_stdin_secret(
        password, password_stdin, value_flag="--password", stdin_flag="--password-stdin"
    )
    otp = read_stdin_secret(
        static_otp_code,
        static_otp_code_stdin,
        value_flag="--static-otp-code",
        stdin_flag="--static-otp-code-stdin",
    )

    body: dict[str, Any] = {"name": name}
    if username is not None:
        body["username"] = username
    if pwd is not None:
        body["password"] = pwd
    if phone_number is not None:
        body["phone_number"] = phone_number
    if otp is not None:
        body["static_otp_code"] = otp
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
