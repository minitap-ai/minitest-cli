from typing import Annotated, Any

import typer

CardNumberOption = Annotated[
    str | None,
    typer.Option(
        "--test-card-number",
        help="Sandbox payment card number the persona pays with (e.g. 4242 4242 4242 4242).",
    ),
]
CardExpiryOption = Annotated[
    str | None, typer.Option("--test-card-expiry", help="Test card expiry, MM/YY or MM/YYYY.")
]
CardCvcOption = Annotated[
    str | None, typer.Option("--test-card-cvc", help="Test card 3 or 4 digit security code.")
]
CardHolderNameOption = Annotated[
    str | None, typer.Option("--test-card-holder-name", help="Name on the test card.")
]
CardPostalCodeOption = Annotated[
    str | None, typer.Option("--test-card-postal-code", help="Test card billing postal code.")
]

_API_KEYS: dict[str, str] = {"holderName": "holder_name", "postalCode": "postal_code"}


def card_fields(
    number: str | None,
    expiry: str | None,
    cvc: str | None,
    holder_name: str | None,
    postal_code: str | None,
) -> dict[str, str]:
    """The card fields the command was given, in the API's shape."""
    given = {
        "number": number,
        "expiry": expiry,
        "cvc": cvc,
        "holder_name": holder_name,
        "postal_code": postal_code,
    }
    return {key: value for key, value in given.items() if value is not None}


def merged_card(stored: dict[str, Any] | None, changes: dict[str, str]) -> dict[str, str]:
    """The stored card with ``changes`` applied, since the API replaces a card whole."""
    items: dict[str, Any] = stored or {}
    current = {_API_KEYS.get(key, key): str(value) for key, value in items.items() if value}
    return {**current, **changes}
