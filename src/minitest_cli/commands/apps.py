"""App management commands: list."""

import asyncio

import httpx
import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.core.auth import require_auth
from minitest_cli.core.config import Settings
from minitest_cli.models.app import AppListResponse
from minitest_cli.utils.output import print_error, print_json, print_table

EXIT_NETWORK_ERROR = 3

app = typer.Typer(name="apps", help="App management.")


@app.callback()
def _callback() -> None:
    """App management."""


APP_TABLE_HEADERS = ["ID", "Name", "Platform"]

_PLATFORM_LABELS: dict[str, str] = {
    "android": "Android",
    "ios": "iOS",
    "cross_platform": "Cross-platform",
}


def _format_platform(value: str | None) -> str:
    """Render an AppPlatform value for the table; pass through unknown values."""
    if value is None:
        return "—"
    return _PLATFORM_LABELS.get(value, value)


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

    rows = [[a.id, a.name, _format_platform(a.platform)] for a in data.apps]
    print_table(APP_TABLE_HEADERS, rows, title="Apps")
