"""Tenant listing and resolution helpers.

The CLI talks to multiple backend services. The list of tenants the user
belongs to is owned by ``minihands-integrations`` (``GET /api/v1/tenants``).

Resolution rules (used by commands that take an optional ``--tenant`` flag):

1. If the caller passed a tenant id, return it.
2. Otherwise list the user's tenants:
   - 0 tenants  -> error: the user has no tenant.
   - 1 tenant   -> return it silently.
   - 2+ tenants -> if stdin is a TTY, prompt; if not, error and ask the
     caller to pass ``--tenant`` explicitly.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import httpx
import typer

from minitest_cli.core.auth import load_token
from minitest_cli.core.config import Settings
from minitest_cli.models.app import TenantResponse
from minitest_cli.utils.output import err_console, print_error

if TYPE_CHECKING:
    from collections.abc import Sequence

CHANNEL_HEADER = "X-Minitest-Channel"
CHANNEL_VALUE = "cli"
DEFAULT_TIMEOUT = 30.0

EXIT_GENERAL_ERROR = 1
EXIT_NETWORK_ERROR = 3


def _stdin_is_tty() -> bool:
    """Return True iff stdin is connected to a TTY.

    Wrapped in a small helper so tests can monkey-patch it without
    interfering with click/typer's CliRunner stdin redirection.
    """
    return sys.stdin.isatty()


async def fetch_user_tenants(settings: Settings) -> list[TenantResponse]:
    """Fetch the tenants the authenticated user belongs to.

    Hits ``GET /api/v1/tenants`` on minihands-integrations. Auth and channel
    headers are injected the same way as the other CLI clients.
    """
    token = load_token(settings)
    async with httpx.AsyncClient(
        base_url=settings.integrations_url,
        headers={
            "Authorization": f"Bearer {token}",
            CHANNEL_HEADER: CHANNEL_VALUE,
        },
        timeout=DEFAULT_TIMEOUT,
    ) as client:
        resp = await client.get("/api/v1/tenants")

    if resp.status_code >= 400:
        detail: str = resp.text
        try:
            body = resp.json()
            if isinstance(body, dict):
                detail = str(body.get("detail") or body.get("message") or detail)
        except Exception:  # noqa: BLE001
            pass
        print_error(f"Failed to list tenants ({resp.status_code}): {detail}")
        raise typer.Exit(code=EXIT_NETWORK_ERROR)

    payload = resp.json()
    if not isinstance(payload, list):
        print_error("Unexpected tenants response: expected a JSON array.")
        raise typer.Exit(code=EXIT_NETWORK_ERROR)
    return [TenantResponse.model_validate(item) for item in payload]


def _prompt_tenant_choice(tenants: Sequence[TenantResponse]) -> TenantResponse:
    """Prompt the user to pick a tenant from the list. Stdin must be a TTY."""
    err_console.print("[bold]Available tenants:[/bold]")
    for idx, tenant in enumerate(tenants, start=1):
        err_console.print(f"  [cyan]{idx}[/cyan]) {tenant.name} [dim]({tenant.id})[/dim]")

    while True:
        choice = typer.prompt("Pick a tenant by number", err=True, type=str).strip()
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(tenants):
                return tenants[idx - 1]
        err_console.print(
            f"[bold red]Invalid choice.[/bold red] Pick a number between 1 and {len(tenants)}."
        )


def resolve_tenant_id(
    settings: Settings,
    explicit_tenant_id: str | None,
    tenants: Sequence[TenantResponse],
) -> str:
    """Resolve the tenant id to use given an optional explicit value and fetched tenants.

    Errors out with a clear message and a non-zero exit code when:
    - the user has no tenants;
    - multiple tenants are available and stdin is not a TTY.
    """
    if explicit_tenant_id:
        return explicit_tenant_id

    if not tenants:
        print_error("You don't belong to any tenant. Create one in the Minitap web app first.")
        raise typer.Exit(code=EXIT_GENERAL_ERROR)

    if len(tenants) == 1:
        return tenants[0].id

    if not _stdin_is_tty():
        names = ", ".join(f"{t.name} ({t.id})" for t in tenants)
        print_error(f"Multiple tenants available; pass --tenant <id> explicitly. Tenants: {names}")
        raise typer.Exit(code=EXIT_GENERAL_ERROR)

    chosen = _prompt_tenant_choice(tenants)
    return chosen.id
