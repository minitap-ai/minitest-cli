"""App management commands: list, create."""

import asyncio
from pathlib import Path
from typing import Annotated

import httpx
import typer

from minitest_cli.api.apps_manager_client import AppsManagerClient  # noqa: F401  re-exported for tests
from minitest_cli.api.client import ApiClient
from minitest_cli.commands.apps_helpers import create_app_request
from minitest_cli.core.auth import require_auth
from minitest_cli.core.config import Settings
from minitest_cli.core.tenants import fetch_user_tenants, resolve_tenant_id
from minitest_cli.models.app import AppDetailResponse, AppListResponse, AppPlatform
from minitest_cli.utils.output import (
    err_console,
    print_error,
    print_json,
    print_success,
    print_table,
)

EXIT_NETWORK_ERROR = 3

app = typer.Typer(name="apps", help="App management.")


@app.callback()
def _callback() -> None:
    """App management."""


APP_TABLE_HEADERS = ["ID", "Name", "Platform"]

_PLATFORM_LABELS: dict[str, str] = {
    "android": "Android",
    "ios": "iOS",
    "web": "Web",
}


def _format_platforms(values: list[str]) -> str:
    """Render an app's platform lanes for the table."""
    if not values:
        return "—"
    return ", ".join(_PLATFORM_LABELS.get(v, v) for v in values)


def _get_settings() -> Settings:
    return typer.Context.settings  # type: ignore[attr-defined]


def _is_json_mode() -> bool:
    return typer.Context.json_mode  # type: ignore[attr-defined]


@app.command(name="list")
def list_apps() -> None:
    """List all apps."""
    settings = _get_settings()
    json_mode = _is_json_mode()
    require_auth(settings)

    async def _list() -> AppListResponse:
        async with ApiClient(settings) as client:
            resp = await client.get("/api/v1/apps")
            if resp.status_code >= 400:
                detail = resp.text
                try:
                    body = resp.json()
                    if isinstance(body, dict):
                        detail = body.get("detail") or body.get("message") or detail
                except Exception:  # noqa: BLE001
                    pass
                print_error(f"API error ({resp.status_code}): {detail}")
                raise typer.Exit(code=EXIT_NETWORK_ERROR)
            return AppListResponse.model_validate(resp.json())

    try:
        data = asyncio.run(_list())
    except httpx.HTTPError as exc:
        print_error(f"Network error: {exc}")
        raise typer.Exit(code=EXIT_NETWORK_ERROR) from exc

    if json_mode:
        print_json([a.model_dump(mode="json", by_alias=True) for a in data.apps])
        return

    rows = [[a.id, a.name, _format_platforms(a.platforms)] for a in data.apps]
    print_table(APP_TABLE_HEADERS, rows, title="Apps")


@app.command(name="create")
def create_app(
    name: Annotated[
        str,
        typer.Option(
            "--name",
            help="Human-readable app name.",
        ),
    ],
    tenant: Annotated[
        str | None,
        typer.Option(
            "--tenant",
            help=(
                "Tenant ID to create the app under. Auto-resolved when the user has a "
                "single tenant; prompts on a TTY otherwise."
            ),
        ),
    ] = None,
    description: Annotated[
        str | None,
        typer.Option("--description", help="Optional description."),
    ] = None,
    slug: Annotated[
        str | None,
        typer.Option(
            "--slug",
            help="URL-friendly slug. Auto-generated from the name if omitted.",
        ),
    ] = None,
    platform: Annotated[
        list[AppPlatform] | None,
        typer.Option(
            "--platform",
            help="Platform lane (repeatable): ios, android, or web. At least one required.",
        ),
    ] = None,
    web_url: Annotated[
        str | None,
        typer.Option("--web-url", help="Web/PWA URL the app is reachable at (for --platform web)."),
    ] = None,
    icon: Annotated[
        Path | None,
        typer.Option(
            "--icon",
            help="Optional path to an icon image to upload.",
            exists=True,
            readable=True,
            dir_okay=False,
        ),
    ] = None,
) -> None:
    """Create a new app on a tenant.

    Calls ``POST /api/v1/tenants/{tenant_id}/apps`` on apps-manager. Prints the
    created app's id to stdout; with ``--json``, prints the full record.
    """
    settings = _get_settings()
    json_mode = _is_json_mode()
    require_auth(settings)

    if not platform:
        print_error("Select at least one --platform: ios, android, or web.")
        raise typer.Exit(code=1)

    async def _run() -> AppDetailResponse:
        if tenant:
            resolved_tenant_id = tenant
        else:
            tenants = await fetch_user_tenants(settings)
            resolved_tenant_id = resolve_tenant_id(settings, None, tenants)
            if len(tenants) > 1:
                err_console.print(f"[dim]Using tenant {resolved_tenant_id}[/dim]")

        return await create_app_request(
            settings,
            tenant_id=resolved_tenant_id,
            name=name,
            platforms=[p.value for p in platform],
            web_url=web_url,
            description=description,
            slug=slug,
            icon=icon,
        )

    try:
        created = asyncio.run(_run())
    except httpx.HTTPError as exc:
        print_error(f"Network error: {exc}")
        raise typer.Exit(code=EXIT_NETWORK_ERROR) from exc

    if json_mode:
        print_json(created.model_dump(mode="json", by_alias=True))
        return

    print_success(f"Created app '{created.name}' (slug: {created.slug})")
    print(created.id)  # noqa: T201
