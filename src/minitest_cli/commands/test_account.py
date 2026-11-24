"""`minitest test-account`: the real logins of a persona."""

from typing import Annotated, Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands import test_profile_update
from minitest_cli.commands.persona_helpers import (
    current_app_id,
    accounts_path,
    handle_persona_response,
    personas_path,
    resolve_persona_id,
)
from minitest_cli.commands.test_profile_card import (
    CardCvcOption,
    CardExpiryOption,
    CardHolderNameOption,
    CardNumberOption,
    CardPostalCodeOption,
    card_fields,
)
from minitest_cli.commands.test_profile_helpers import (
    get_settings,
    is_json_mode,
    read_stdin_secret,
    run_api_call,
)
from minitest_cli.commands.test_profile_secret_refs import (
    CardSecretOption,
    OtpSecretOption,
    PasswordSecretOption,
    secret_ref_fields,
)
from minitest_cli.utils.output import output, print_error, print_success

app = typer.Typer(
    name="test-account",
    help="Manage test accounts: the real logins of a persona (`minitest persona`). "
    "Mini signs in with one of a persona's accounts, spreading runs across them.",
)
test_profile_update.register(app, label="Test account")

PersonaOption = Annotated[str, typer.Option("--persona", help="Persona ID or name.")]
AccountArg = Annotated[str, typer.Argument(help="Test account ID.")]


@app.command(name="add")
def add_account(
    persona: PersonaOption,
    name: Annotated[
        str | None,
        typer.Option("--name", help="Account label; defaults to the persona name, numbered."),
    ] = None,
    username: Annotated[
        str | None,
        typer.Option(
            "--username",
            help="Login. <prefix>@qa.minitap.ai without password for email-OTP accounts.",
        ),
    ] = None,
    password: Annotated[
        str | None, typer.Option("--password", help="Password (prefer --password-stdin).")
    ] = None,
    password_stdin: Annotated[
        bool, typer.Option("--password-stdin", help="Read the password from stdin.")
    ] = False,
    phone_number: Annotated[
        str | None, typer.Option("--phone-number", help="E.164 number for phone-OTP logins.")
    ] = None,
    static_otp_code: Annotated[
        str | None, typer.Option("--static-otp-code", help="Fixed OTP code (prefer stdin).")
    ] = None,
    static_otp_code_stdin: Annotated[
        bool, typer.Option("--static-otp-code-stdin", help="Read the static OTP code from stdin.")
    ] = False,
    test_card_number: CardNumberOption = None,
    test_card_expiry: CardExpiryOption = None,
    test_card_cvc: CardCvcOption = None,
    test_card_holder_name: CardHolderNameOption = None,
    test_card_postal_code: CardPostalCodeOption = None,
    password_secret: PasswordSecretOption = None,
    otp_secret: OtpSecretOption = None,
    card_secret: CardSecretOption = None,
) -> None:
    """Add a test account to a persona; it takes the persona's exclusive use."""
    app_id = current_app_id()
    pwd = read_stdin_secret(
        password, password_stdin, value_flag="--password", stdin_flag="--password-stdin"
    )
    otp = read_stdin_secret(
        static_otp_code,
        static_otp_code_stdin,
        value_flag="--static-otp-code",
        stdin_flag="--static-otp-code-stdin",
    )
    card = card_fields(
        test_card_number,
        test_card_expiry,
        test_card_cvc,
        test_card_holder_name,
        test_card_postal_code,
    )
    given = {
        "name": name,
        "username": username,
        "password": pwd,
        "phoneNumber": phone_number,
        "staticOtpCode": otp,
        "testCard": card or None,
    }
    body: dict[str, Any] = {key: value for key, value in given.items() if value is not None}
    body |= secret_ref_fields(
        password_secret,
        otp_secret,
        card_secret,
        password_given=pwd is not None,
        otp_given=otp is not None,
        card_given=bool(card),
    )

    async def _run() -> Any:
        async with ApiClient(get_settings()) as client:
            persona_id = await resolve_persona_id(client, app_id, persona)
            resp = await client.post(f"{personas_path(app_id)}/{persona_id}/accounts", json=body)
            handle_persona_response(resp)
            return resp.json()

    data = run_api_call(_run())
    if not is_json_mode():
        print_success(f"Test account added: {data['id']} ({data['name']})")
    output(data, json_mode=is_json_mode())


@app.command(name="move")
def move_account(account: AccountArg, persona: PersonaOption) -> None:
    """Move a test account to another persona; its scenarios keep the persona they play."""
    app_id = current_app_id()

    async def _run() -> Any:
        async with ApiClient(get_settings()) as client:
            persona_id = await resolve_persona_id(client, app_id, persona)
            resp = await client.put(
                f"{accounts_path(app_id)}/{account}/persona", json={"personaId": persona_id}
            )
            handle_persona_response(resp, resource="Test account")
            return resp.json()

    data = run_api_call(_run())
    if not is_json_mode():
        print_success(f"Test account {account} moved to persona {data['personaId']}.")
    output(data, json_mode=is_json_mode())


@app.command(name="remove")
def remove_account(
    account: AccountArg,
    force: Annotated[bool, typer.Option("--force", help="Skip confirmation.")] = False,
) -> None:
    """Remove a test account; its scenarios move to another account of the persona first."""
    if not force:
        print_error("Remove requires --force flag.")
        raise typer.Exit(code=1)
    app_id = current_app_id()

    async def _run() -> None:
        async with ApiClient(get_settings()) as client:
            resp = await client.delete(f"{accounts_path(app_id)}/{account}")
            handle_persona_response(resp, resource="Test account")

    run_api_call(_run())
    if is_json_mode():
        output({"deleted": True, "id": account}, json_mode=True)
    else:
        print_success(f"Test account removed: {account}")


@app.command(name="clear-cooldown")
def clear_cooldown(account: AccountArg) -> None:
    """Make a cooling-down test account available to runs again now."""
    app_id = current_app_id()

    async def _run() -> Any:
        async with ApiClient(get_settings()) as client:
            resp = await client.delete(f"{accounts_path(app_id)}/{account}/cooldown")
            handle_persona_response(resp, resource="Test account")
            return resp.json()

    data = run_api_call(_run())
    if not is_json_mode():
        print_success(f"Cooldown cleared on test account {account}.")
    output(data, json_mode=is_json_mode())
