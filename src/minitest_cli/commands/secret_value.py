"""Read a secret value from stdin (or a hidden prompt) into the API body shape.

Error messages here never echo the value, only its name and shape.
"""

from __future__ import annotations

import getpass
import json
import re
import sys
from typing import Any, NoReturn

import typer

from minitest_cli.commands.secret_helpers import CARD_FIELDS, SecretKind
from minitest_cli.utils.output import print_error

_REQUIRED_CARD_FIELDS = ("number", "expiry", "cvc")
_CAMEL_CARD_FIELDS = {"holderName": "holder_name", "postalCode": "postal_code"}
_BASE32 = re.compile(r"^[A-Z2-7]+=*$")


def stdin_is_tty() -> bool:
    return sys.stdin.isatty()


def _fail(message: str) -> NoReturn:
    print_error(message)
    raise typer.Exit(code=1)


def _check_totp(value: str) -> None:
    if value.lower().startswith("otpauth://"):
        return
    if not _BASE32.match(value.replace(" ", "").upper()):
        _fail("An OTP seed must be a base32 string or an otpauth:// URL.")


def parse_card(raw: str) -> dict[str, str]:
    """Card fields from a JSON object: number, expiry, cvc, optional holder_name, postal_code."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = None
    if not isinstance(data, dict):
        _fail(
            'A card is read as a JSON object on stdin, e.g. {"number": "…", "expiry": "12/34", '
            '"cvc": "…"} (optional: holder_name, postal_code).'
        )
    fields = {_CAMEL_CARD_FIELDS.get(str(k), str(k)): v for k, v in data.items()}
    unknown = sorted(set(fields) - set(CARD_FIELDS))
    if unknown:
        _fail(f"Unknown card field(s): {', '.join(unknown)}. Allowed: {', '.join(CARD_FIELDS)}.")
    if any(not isinstance(v, str | int) for v in fields.values()):
        _fail("Every card field must be a string.")
    card = {k: str(v).strip() for k, v in fields.items() if str(v).strip()}
    missing = [k for k in _REQUIRED_CARD_FIELDS if k not in card]
    if missing:
        _fail(f"Missing card field(s): {', '.join(missing)}.")
    return card


def _prompt_card(name: str) -> dict[str, str]:
    card: dict[str, str] = {}
    for field in CARD_FIELDS:
        optional = field not in _REQUIRED_CARD_FIELDS
        label = f"{name}.{field}{' (optional, Enter to skip)' if optional else ''}: "
        value = getpass.getpass(label).strip()
        if value:
            card[field] = value
        elif not optional:
            _fail(f"Missing card field: {field}.")
    return card


def _prompt_value(name: str) -> str:
    value = getpass.getpass(f"Value of {name} (hidden): ")
    if getpass.getpass("Repeat the value: ") != value:
        _fail("The two values differ, nothing was saved.")
    return value


def read_secret_body(name: str, kind: SecretKind, *, interactive: bool) -> dict[str, Any]:
    """``{"value": …}`` or ``{"fields": …}`` for a PUT, read from stdin or a hidden prompt."""
    if interactive:
        if not stdin_is_tty():
            _fail("--interactive needs a terminal; pipe the value on stdin instead.")
        if kind is SecretKind.card:
            return {"fields": _prompt_card(name)}
        value = _prompt_value(name).strip()
    else:
        if stdin_is_tty():
            _fail(
                f"Pipe the value of {name} on stdin, e.g. printf '%s' \"$V\" | minitest secret set "
                f"{name} --kind {kind.value} (or use --interactive for a hidden prompt)."
            )
        raw = sys.stdin.read()
        if kind is SecretKind.card:
            return {"fields": parse_card(raw)}
        value = raw.rstrip("\r\n")
    if not value:
        _fail(f"Empty value for {name}: nothing was saved.")
    if kind is SecretKind.totp:
        _check_totp(value)
    return {"value": value}
