"""Shared helpers for the `persona` and `test-account` commands."""

from typing import Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.run_helpers import is_uuid
from minitest_cli.commands.test_profile_helpers import (
    get_app_flag,
    get_settings,
    handle_profile_response,
)
from minitest_cli.core.app_context import resolve_app_id
from minitest_cli.core.auth import require_auth
from minitest_cli.utils.output import print_error

PERSONA_TABLE_HEADERS = ["ID", "Name", "Accounts", "Scenarios", "Exclusive use", "Kind"]
ACCOUNT_TABLE_HEADERS = ["ID", "Name", "Login", "Credentials"]
POOL_TABLE_HEADERS = [*ACCOUNT_TABLE_HEADERS, "State"]


def current_app_id() -> str:
    settings = get_settings()
    require_auth(settings)
    return resolve_app_id(settings, get_app_flag())


def personas_path(app_id: str) -> str:
    return f"/api/v1/apps/{app_id}/personas"


def accounts_path(app_id: str) -> str:
    return f"/api/v1/apps/{app_id}/test-accounts"


def handle_persona_response(resp: Any, *, resource: str = "Persona") -> None:
    handle_profile_response(resp, resource=resource)


async def resolve_persona_id(client: ApiClient, app_id: str, ref: str) -> str:
    """A persona ID as given, or the ID of the persona named ``ref`` (case-insensitive)."""
    if is_uuid(ref):
        return ref
    resp = await client.get(personas_path(app_id))
    handle_persona_response(resp)
    matches = [p for p in resp.json()["items"] if p["name"].casefold() == ref.casefold()]
    if not matches:
        print_error(f"No persona named '{ref}'. List them with `minitest persona list`.")
        raise typer.Exit(code=4)
    return matches[0]["id"]


def format_persona_row(persona: dict[str, Any]) -> list[str]:
    return [
        persona["id"],
        persona["name"],
        str(persona.get("accountCount", "")),
        str(persona.get("scenarioCount", "")),
        "on" if persona.get("exclusiveUse") else "off",
        persona.get("kind", ""),
    ]


def credentials_label(account: dict[str, Any]) -> str:
    held = [
        label
        for key, label in (
            ("hasPassword", "password"),
            ("hasStaticOtpCode", "OTP"),
            ("hasTestCard", "card"),
        )
        if account.get(key)
    ]
    return ", ".join(held) or "none"


def account_state(state: str, account: dict[str, Any], holders: list[dict[str, Any]]) -> str:
    if state == "in_use":
        runs = [
            f"run {h['subdagRunId']} · {h['platform']}"
            if h.get("subdagRunId")
            else "another workspace"
            for h in holders
        ]
        return "In use by " + ", ".join(runs)
    if state == "cooling_down":
        return (
            f"Cooling down until {account.get('cooldownUntil')} ({account.get('cooldownReason')})"
        )
    return "Free"


def format_account_row(account: dict[str, Any]) -> list[str]:
    return [
        account["id"],
        account["name"],
        account.get("username") or account.get("phoneNumber") or "",
        credentials_label(account),
    ]


def format_pool_row(entry: dict[str, Any]) -> list[str]:
    account = entry["account"]
    return [*format_account_row(account), account_state(entry["state"], account, entry["holders"])]
