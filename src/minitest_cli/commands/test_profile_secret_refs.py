"""``--password-secret/--otp-secret/--card-secret``: point a persona at vault secrets."""

from typing import Annotated, Any

import typer

from minitest_cli.commands.secret_helpers import validate_name
from minitest_cli.utils.output import print_error

_CLEAR_HINT = " Pass an empty string on update to stop using it."

PasswordSecretOption = Annotated[
    str | None,
    typer.Option(
        "--password-secret",
        help="Name of a password secret (minitest secret) to log in with." + _CLEAR_HINT,
    ),
]
OtpSecretOption = Annotated[
    str | None,
    typer.Option(
        "--otp-secret",
        help="Name of an OTP seed (totp) or fixed-code (text) secret." + _CLEAR_HINT,
    ),
]
CardSecretOption = Annotated[
    str | None,
    typer.Option("--card-secret", help="Name of a card secret to pay with." + _CLEAR_HINT),
]


def secret_ref_fields(
    password_secret: str | None,
    otp_secret: str | None,
    card_secret: str | None,
    *,
    password_given: bool,
    otp_given: bool,
    card_given: bool,
) -> dict[str, Any]:
    """API fields for the secret pointers; ``""`` clears one. Rejects mixing with raw values."""
    fields: dict[str, Any] = {}
    for key, value, raw_given, flag, raw_flag in (
        ("passwordSecret", password_secret, password_given, "--password-secret", "--password"),
        ("otpSecret", otp_secret, otp_given, "--otp-secret", "--static-otp-code"),
        ("cardSecret", card_secret, card_given, "--card-secret", "--test-card-*"),
    ):
        if value is None:
            continue
        if raw_given:
            print_error(f"Use either {flag} or {raw_flag}, not both.")
            raise typer.Exit(code=1)
        fields[key] = validate_name(value) if value else None
    return fields
