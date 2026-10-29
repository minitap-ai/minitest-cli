"""Shared plumbing for `minitest draft`: target resolution, Conductor calls, error mapping.

A draft here is a Conductor workbench: a branch of the suite plus Mini's conversation
about it. Conductor owns it, so these commands talk to MINITEST_CONDUCTOR_URL rather
than the testing-service API the low-level `minitest df` commands use.
"""

import asyncio
from collections.abc import Coroutine
from dataclasses import dataclass
from typing import Any

import httpx
import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.api.errors import format_network_error
from minitest_cli.commands.env_helpers import resolve_app_and_tenant
from minitest_cli.commands.run_helpers import (
    ensure_uuid,
    extract_detail,
    get_app_flag,
    get_settings,
    is_json_mode,
)
from minitest_cli.core.auth import require_auth
from minitest_cli.core.config import Settings
from minitest_cli.utils.output import print_error, print_info

EXIT_GENERAL_ERROR = 1
EXIT_NETWORK_ERROR = 3
EXIT_NOT_FOUND = 4
EXIT_CONFLICT = 6

DRAFTS_PATH = "/api/v1/drafts"
# Transport failures and 5xx on a write are retried with the same idempotency id, so
# the retry lands on the first attempt's draft or message instead of making another.
WRITE_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 1.0


@dataclass(frozen=True)
class DraftTarget:
    settings: Settings
    app_id: str
    tenant_id: str
    json_mode: bool

    @property
    def params(self) -> dict[str, str]:
        return {"tenantId": self.tenant_id}


def resolve_target() -> DraftTarget:
    """Resolve auth, the active app and its tenant; exits on failure."""
    settings = get_settings()
    require_auth(settings)
    app_id, tenant_id = run_conductor(resolve_app_and_tenant(settings, get_app_flag()))
    return DraftTarget(settings, app_id, tenant_id, is_json_mode())


def draft_path(draft_id: str, suffix: str = "") -> str:
    ensure_uuid(draft_id, kind="draft id")
    return f"{DRAFTS_PATH}/{draft_id}{suffix}"


def run_conductor[T](coro: Coroutine[Any, Any, T]) -> T:
    try:
        return asyncio.run(coro)
    except httpx.HTTPError as exc:
        print_error(format_network_error(exc))
        raise typer.Exit(code=EXIT_NETWORK_ERROR) from exc


async def _send(
    target: DraftTarget, method: str, path: str, *, retry: bool, **kwargs: Any
) -> httpx.Response:
    attempts = WRITE_ATTEMPTS if retry else 1
    params = {**target.params, **kwargs.pop("params", {})}
    async with ApiClient(target.settings, base_url=target.settings.conductor_url) as client:
        for attempt in range(1, attempts + 1):
            try:
                resp = await client.request(method, path, params=params, **kwargs)
            except httpx.TransportError:
                if attempt == attempts:
                    raise
            else:
                if resp.status_code < 500 or attempt == attempts:
                    return resp
            await asyncio.sleep(RETRY_DELAY_SECONDS * attempt)
    raise RuntimeError("unreachable")


def call(
    target: DraftTarget,
    method: str,
    path: str,
    *,
    resource: str = "Draft",
    retry: bool = False,
    **kwargs: Any,
) -> Any:
    """Send one request to Conductor and return its JSON body, exiting on any error.

    Only pass ``retry=True`` for requests carrying an idempotency id (or reads).
    """
    resp = run_conductor(_send(target, method, path, retry=retry, **kwargs))
    raise_for_status(resp, resource=resource)
    return resp.json()


DRAFT_CONFLICT_HINT = "Re-read it with `minitest draft get <id>` before deciding what to do next."


def raise_for_status(
    resp: httpx.Response, *, resource: str, conflict_hint: str = DRAFT_CONFLICT_HINT
) -> None:
    """Map a Conductor error to the exit code that says what the caller should do next."""
    if resp.status_code < 400:
        return
    detail = extract_detail(resp)
    if resp.status_code in (401, 403):
        print_error(f"Not allowed ({resp.status_code}): {detail or 'credentials rejected.'}")
        raise typer.Exit(code=EXIT_GENERAL_ERROR)
    if resp.status_code == 404:
        print_error(detail or f"{resource} not found.")
        raise typer.Exit(code=EXIT_NOT_FOUND)
    if resp.status_code == 409:
        print_error(detail or f"{resource} cannot do that in its current state.")
        print_info(conflict_hint)
        raise typer.Exit(code=EXIT_CONFLICT)
    if resp.status_code in (400, 422):
        print_error(detail or f"Invalid request ({resp.status_code}).")
        raise typer.Exit(code=EXIT_GENERAL_ERROR)
    print_error(detail or f"Conductor error: {resp.status_code}")
    raise typer.Exit(code=EXIT_NETWORK_ERROR)
