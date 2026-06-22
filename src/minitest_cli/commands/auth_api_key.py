"""Tenant-scoped Minitest API key commands: mint, list, revoke."""

from __future__ import annotations

import asyncio
from typing import Annotated
from uuid import UUID

import typer
from rich.console import Console
from rich.table import Table

from minitest_cli.api.client import ApiClient
from minitest_cli.core.auth import load_or_refresh_credentials
from minitest_cli.core.config import Settings, get_settings
from minitest_cli.utils.output import print_json

app = typer.Typer(name="api-key", help="Manage tenant-scoped Minitest API keys (mtk_…)")

err_console = Console(stderr=True)


def _ensure_oauth(settings: Settings) -> str:
    """Return a bearer token, refusing when only MINITEST_API_KEY is configured.

    Minting/revoking keys requires OAuth (or MINITEST_TOKEN); an mtk_ key cannot
    manage other keys.
    """
    if settings.token:
        return settings.token
    creds = load_or_refresh_credentials(settings)
    if creds is not None:
        return creds.access_token
    err_console.print(
        "[bold red]Error:[/bold red] Managing API keys requires OAuth login or "
        "MINITEST_TOKEN. An mtk_ API key cannot manage keys."
    )
    raise typer.Exit(code=2)


@app.command()
def mint(
    tenant: Annotated[UUID, typer.Option("--tenant", help="Tenant UUID")],
    name: Annotated[str, typer.Option("--name", help="Human-readable label")],
    as_json: Annotated[bool, typer.Option("--json", help="Emit JSON to stdout")] = False,
) -> None:
    """Mint a new tenant-scoped API key. The plaintext token is shown only once."""
    settings = get_settings()
    token = _ensure_oauth(settings)

    async def _mint() -> dict:
        async with ApiClient(settings, token_override=token) as client:
            response = await client.post(
                f"/api/v1/tenants/{tenant}/minitest-api-keys",
                json={"name": name},
            )
            response.raise_for_status()
            return response.json()

    payload = asyncio.run(_mint())
    plaintext = payload["plaintextToken"]

    if as_json:
        print_json(payload)
        return

    err_console.print("[bold yellow]Store this key now. It will NOT be shown again.[/bold yellow]")
    # Use the builtin print (not Rich) so the secret is emitted verbatim, with no
    # ANSI styling or wrapping that could corrupt it when piped into a secret store.
    print(plaintext)  # noqa: T201


@app.command(name="list")
def list_keys(
    tenant: Annotated[UUID, typer.Option("--tenant", help="Tenant UUID")],
    as_json: Annotated[bool, typer.Option("--json", help="Emit JSON to stdout")] = False,
) -> None:
    """List the tenant's API keys (prefixes only; plaintext is never stored)."""
    settings = get_settings()
    token = _ensure_oauth(settings)

    async def _list() -> list[dict]:
        async with ApiClient(settings, token_override=token) as client:
            response = await client.get(f"/api/v1/tenants/{tenant}/minitest-api-keys")
            response.raise_for_status()
            return response.json()

    rows = asyncio.run(_list())

    if as_json:
        print_json(rows)
        return

    table = Table(title="API keys", show_header=True, header_style="bold")
    for header in ("Key ID", "Name", "Prefix", "Created", "Last used"):
        table.add_column(header)
    for r in rows:
        table.add_row(
            r["keyId"],
            r["name"],
            r["keyPrefix"],
            r["createdAt"],
            r.get("lastUsedAt") or "—",
        )
    Console().print(table)


@app.command()
def revoke(
    tenant: Annotated[UUID, typer.Option("--tenant", help="Tenant UUID")],
    key: Annotated[UUID, typer.Option("--key", help="Key ID to revoke")],
    as_json: Annotated[bool, typer.Option("--json", help="Emit JSON to stdout")] = False,
) -> None:
    """Revoke (delete) a tenant API key by its key ID."""
    settings = get_settings()
    token = _ensure_oauth(settings)

    async def _revoke() -> None:
        async with ApiClient(settings, token_override=token) as client:
            response = await client.delete(f"/api/v1/tenants/{tenant}/minitest-api-keys/{key}")
            response.raise_for_status()

    asyncio.run(_revoke())

    if as_json:
        print_json({"revoked": True, "keyId": str(key)})
        return

    Console().print(f"[bold green]Revoked key {key}[/bold green]")
