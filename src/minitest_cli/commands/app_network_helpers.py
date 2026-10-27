"""Shared plumbing for the per-app network settings (residential proxy, private network)."""

import asyncio
import re
from typing import Any

import httpx
import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.api.errors import format_network_error
from minitest_cli.commands._response_errors import extract_detail
from minitest_cli.core.app_context import resolve_app_id
from minitest_cli.core.auth import require_auth
from minitest_cli.core.config import Settings
from minitest_cli.utils.output import print_error

EXIT_GENERAL_ERROR = 1
EXIT_AUTH_ERROR = 2
EXIT_NETWORK_ERROR = 3
EXIT_NOT_FOUND = 4

ADMIN_ONLY_MESSAGE = "Only workspace owners and admins can change this setting."


def is_json_mode() -> bool:
    return typer.Context.json_mode  # type: ignore[attr-defined]


def resolve_target() -> tuple[Settings, str]:
    settings: Settings = typer.Context.settings  # type: ignore[attr-defined]
    require_auth(settings)
    return settings, resolve_app_id(settings, typer.Context.app_flag)  # type: ignore[attr-defined]


def fail(message: str, code: int = EXIT_GENERAL_ERROR) -> typer.Exit:
    print_error(message)
    return typer.Exit(code=code)


def _raise_for_status(resp: httpx.Response, forbidden: str) -> None:
    if resp.status_code < 400:
        return
    detail = extract_detail(resp)
    if resp.status_code == 403:
        raise fail(f"{forbidden} ({detail})", EXIT_AUTH_ERROR)
    if resp.status_code == 401:
        raise fail(f"Authentication failed: {detail}", EXIT_AUTH_ERROR)
    if resp.status_code == 404:
        raise fail(f"Not found: {detail}", EXIT_NOT_FOUND)
    if resp.status_code in (400, 409, 422):
        raise fail(f"Rejected by the server ({resp.status_code}): {detail}")
    raise fail(f"API error ({resp.status_code}): {detail}", EXIT_NETWORK_ERROR)


def call_api(
    settings: Settings,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    *,
    forbidden: str = ADMIN_ONLY_MESSAGE,
) -> dict[str, Any]:
    async def _run() -> dict[str, Any]:
        async with ApiClient(settings) as client:
            resp = await client.request(method, path, json=body)
        _raise_for_status(resp, forbidden)
        try:
            return resp.json()
        except ValueError as exc:
            raise fail(
                f"Unexpected non-JSON response ({resp.status_code}): {resp.text[:200]}",
                EXIT_NETWORK_ERROR,
            ) from exc

    try:
        return asyncio.run(_run())
    except httpx.HTTPError as exc:
        raise fail(format_network_error(exc), EXIT_NETWORK_ERROR) from exc


def merge_domains(
    current: list[str],
    *,
    add: list[str] | None,
    remove: list[str] | None,
    clear: bool,
    pattern: str,
    max_domains: int,
) -> list[str]:
    """Apply ``--clear-domains``, ``--remove-domain`` then ``--domain`` and validate the result."""
    added = [_normalize(d) for d in add or []]
    invalid = [d for d in added if not re.fullmatch(pattern, d)]
    if invalid:
        raise fail(
            f"Invalid domain(s): {', '.join(invalid)}. Use a lowercase host like api.example.com, "
            "or *.example.com to match its subdomains (not example.com itself)."
        )
    removed = {_normalize(d) for d in remove or []}
    unknown = sorted(removed - set(current))
    if unknown:
        raise fail(f"Not in the current domain list: {', '.join(unknown)}.")
    base = [] if clear else [d for d in current if d not in removed]
    merged = list(dict.fromkeys([*base, *added]))
    if len(merged) > max_domains:
        raise fail(f"Too many domains: {len(merged)} (max {max_domains}).")
    return merged


def _normalize(domain: str) -> str:
    return domain.strip().lower().rstrip(".")


def on_off(value: bool) -> str:
    return "on" if value else "off"


def domain_list(domains: list[str]) -> str:
    return ", ".join(domains) if domains else "-"
