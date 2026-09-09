from typing import Annotated, Any

import typer

from minitest_cli.api.client import ApiClient
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


def register(app: typer.Typer) -> None:

    @app.command(name="update")
    def update_profile(
        profile_id: Annotated[str, typer.Argument(help="Test profile ID.")],
        name: Annotated[str | None, typer.Option("--name", help="New profile name.")] = None,
        username: Annotated[str | None, typer.Option("--username", help="New username.")] = None,
        clear_username: Annotated[
            bool,
            typer.Option("--clear-username", help="Remove the stored username."),
        ] = False,
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
        phone_number: Annotated[
            str | None,
            typer.Option("--phone-number", help="New E.164 phone number (e.g. +14155551234)."),
        ] = None,
        clear_phone_number: Annotated[
            bool,
            typer.Option("--clear-phone-number", help="Remove the stored phone number."),
        ] = False,
        static_otp_code: Annotated[
            str | None,
            typer.Option("--static-otp-code", help="New static OTP code (overrides existing)."),
        ] = None,
        static_otp_code_stdin: Annotated[
            bool,
            typer.Option(
                "--static-otp-code-stdin", help="Read the new static OTP code from stdin."
            ),
        ] = False,
        clear_static_otp_code: Annotated[
            bool,
            typer.Option("--clear-static-otp-code", help="Remove the stored static OTP code."),
        ] = False,
        about: Annotated[str | None, typer.Option("--about", help="New about text.")] = None,
        clear_about: Annotated[
            bool,
            typer.Option("--clear-about", help="Remove the stored about text."),
        ] = False,
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

        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        for key, value, clear, value_flag in (
            ("username", username, clear_username, "--username"),
            ("password", pwd, clear_password, "--password/--password-stdin"),
            ("phone_number", phone_number, clear_phone_number, "--phone-number"),
            (
                "static_otp_code",
                otp,
                clear_static_otp_code,
                "--static-otp-code/--static-otp-code-stdin",
            ),
            ("about", about, clear_about, "--about"),
        ):
            if value is not None and clear:
                print_error(
                    f"Use either {value_flag} or --clear-{key.replace('_', '-')}, not both."
                )
                raise typer.Exit(code=1)
            if value is not None:
                body[key] = value
            elif clear:
                body[key] = None

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
