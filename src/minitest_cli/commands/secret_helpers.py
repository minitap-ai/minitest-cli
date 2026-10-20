"""Shared plumbing for the ``secret`` command group (app Secrets vault)."""

from __future__ import annotations

import os
import re
from enum import StrEnum
from typing import Annotated, Any

import httpx
import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.user_story_helpers import (
    extract_detail,
    get_app_flag,
    get_settings,
    is_json_mode,
    run_api_call,
)
from minitest_cli.core.app_context import resolve_app_id
from minitest_cli.core.auth import require_auth
from minitest_cli.core.config import Settings
from minitest_cli.utils.output import err_console, print_error

EXIT_GENERAL_ERROR = 1
EXIT_AUTH_ERROR = 2
EXIT_NETWORK_ERROR = 3
EXIT_NOT_FOUND = 4
EXIT_IN_USE = 6

SECRETS_DISABLED = "Secrets are not enabled for this workspace yet."
NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
MAX_NAME_LENGTH = 64
RESERVED_PREFIXES = (
    "MAAS_",
    "STORY_RUN_",
    "OC_",
    "DEVICE_",
    "MINITEST_",
    "MINITAP_",
    "OPENCODE_",
)
CARD_FIELDS = ("number", "expiry", "cvc", "holder_name", "postal_code")
AGENT_ENV_VARS = ("MINITAP_SECRETS_SOCKET", "STORY_RUN_ID")


class SecretKind(StrEnum):
    password = "password"
    totp = "totp"
    card = "card"
    token = "token"
    text = "text"


JsonOption = Annotated[bool, typer.Option("--json", help="Output JSON to stdout.")]
KindOption = Annotated[
    SecretKind,
    typer.Option("--kind", help="password, totp (OTP seed), card, token (API token) or text."),
]


def secrets_path(app_id: str) -> str:
    return f"/api/v1/apps/{app_id}/secrets"


def reference(name: str, field: str | None = None) -> str:
    return f"{{{{secret:{name}.{field}}}}}" if field else f"{{{{secret:{name}}}}}"


def command_context(json_flag: bool = False) -> tuple[Settings, bool, str]:
    settings = get_settings()
    require_auth(settings)
    return settings, is_json_mode() or json_flag, resolve_app_id(settings, get_app_flag())


def validate_name(name: str) -> str:
    if len(name) > MAX_NAME_LENGTH or not NAME_PATTERN.match(name):
        print_error(
            f"Invalid secret name {name!r}: use UPPER_SNAKE_CASE (A-Z, 0-9, _), "
            f"starting with a letter, at most {MAX_NAME_LENGTH} characters."
        )
        raise typer.Exit(code=EXIT_GENERAL_ERROR)
    reserved = next((p for p in RESERVED_PREFIXES if name.startswith(p)), None)
    if reserved:
        print_error(f"Secret names cannot start with the reserved prefix {reserved}.")
        raise typer.Exit(code=EXIT_GENERAL_ERROR)
    return name


def refuse_agent_context() -> None:
    """A test agent must never write a value: it asks a human through ``secret request``."""
    if any(os.environ.get(var) for var in AGENT_ENV_VARS):
        print_error(
            "Secret values cannot be written from inside a test run. Ask a human for it with: "
            "minitest secret request NAME --kind <kind> --reason '<why>'"
        )
        raise typer.Exit(code=EXIT_GENERAL_ERROR)


def _is_disabled(resp: httpx.Response, detail: str | None, collection: bool) -> bool:
    if collection or detail is None or detail == "Not Found":
        return True
    lowered = detail.lower()
    return "not enabled" in lowered or "disabled" in lowered


def _print_usages(usages: list[dict[str, Any]]) -> None:
    print_error(f"This secret is still used by {len(usages)} item(s):")
    for usage in usages:
        err_console.print(f"  - {format_usage(usage)}")
    err_console.print("Remove those references first, then retry.")


def handle_secret_response(resp: httpx.Response, *, collection: bool = False) -> None:
    if resp.status_code < 400:
        return
    detail = extract_detail(resp)
    if resp.status_code in (401, 403):
        print_error(f"Authentication failed ({resp.status_code}): {detail or 'forbidden'}")
        raise typer.Exit(code=EXIT_AUTH_ERROR)
    if resp.status_code == 404:
        print_error(SECRETS_DISABLED if _is_disabled(resp, detail, collection) else detail or "")
        raise typer.Exit(code=EXIT_NOT_FOUND)
    if resp.status_code == 409:
        usages = _usages(resp)
        if usages:
            _print_usages(usages)
            raise typer.Exit(code=EXIT_IN_USE)
    print_error(detail or f"API error: {resp.status_code}")
    raise typer.Exit(code=EXIT_NETWORK_ERROR if resp.status_code >= 500 else EXIT_GENERAL_ERROR)


def _usages(resp: httpx.Response) -> list[dict[str, Any]]:
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        return []
    if isinstance(body, dict) and isinstance(body.get("detail"), dict):
        body = body["detail"]
    raw = body.get("usages") if isinstance(body, dict) else None
    return [u for u in raw or [] if isinstance(u, dict)]


async def request(
    client: ApiClient,
    method: str,
    path: str,
    *,
    json: dict[str, Any] | None = None,
    collection: bool = False,
) -> Any:
    resp = await client.request(method, path, json=json)
    handle_secret_response(resp, collection=collection)
    return resp.json() if resp.content else None


def call(
    settings: Settings,
    method: str,
    path: str,
    *,
    json: dict[str, Any] | None = None,
    collection: bool = False,
) -> Any:
    async def _run() -> Any:
        async with ApiClient(settings) as client:
            return await request(client, method, path, json=json, collection=collection)

    return run_api_call(_run())


def format_usage(usage: dict[str, Any]) -> str:
    label = f"{usage.get('type', '')} {usage.get('name') or usage.get('id', '')}".strip()
    return f"{label} ({usage['field']})" if usage.get("field") else label
