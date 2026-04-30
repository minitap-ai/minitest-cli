"""Flow type commands: list valid flow (user-story) types from the backend.

Wraps ``GET /api/v1/user-story-types`` on testing-service. The CLI surface uses
``flow-types`` per the loot orchestration ticket; the underlying backend
endpoint is ``user-story-types`` (renamed in migrations 00050/00051).
"""

import asyncio
from typing import Any

import httpx
import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.core.auth import require_auth
from minitest_cli.core.config import Settings
from minitest_cli.utils.output import print_error, print_json, print_table

EXIT_NETWORK_ERROR = 3

FLOW_TYPES_PATH = "/api/v1/user-story-types"

app = typer.Typer(name="flow-types", help="List valid flow (user-story) types.")


@app.callback()
def _callback() -> None:
    """Flow types operations."""


def _get_settings() -> Settings:
    return typer.Context.settings  # type: ignore[attr-defined]


def _is_json_mode() -> bool:
    return typer.Context.json_mode  # type: ignore[attr-defined]


def _extract_detail(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        if isinstance(body, dict):
            detail = body.get("detail") or body.get("message")
            if detail:
                return str(detail)
    except Exception:  # noqa: BLE001
        pass
    return resp.text or f"HTTP {resp.status_code}"


def _handle_response_error(resp: httpx.Response) -> None:
    if resp.status_code < 400:
        return
    detail = _extract_detail(resp)
    if resp.status_code in (401, 403):
        print_error(f"Authentication failed ({resp.status_code}): {detail}")
        raise typer.Exit(code=1)
    print_error(f"API error ({resp.status_code}): {detail}")
    raise typer.Exit(code=EXIT_NETWORK_ERROR)


@app.command(name="list")
def list_flow_types() -> None:
    """List all valid flow (user-story) types.

    Calls ``GET /api/v1/user-story-types``. Without ``--json``, prints one
    type per line; with ``--json``, prints the raw JSON array.
    """
    settings = _get_settings()
    json_mode = _is_json_mode()
    require_auth(settings)

    async def _run() -> Any:
        async with ApiClient(settings) as client:
            resp = await client.get(FLOW_TYPES_PATH)
            _handle_response_error(resp)
            return resp.json()

    try:
        data = asyncio.run(_run())
    except httpx.HTTPError as exc:
        print_error(f"Network error: {exc}")
        raise typer.Exit(code=EXIT_NETWORK_ERROR) from exc

    if not isinstance(data, list):
        print_error("Unexpected response shape: expected a JSON array.")
        raise typer.Exit(code=EXIT_NETWORK_ERROR)

    if json_mode:
        print_json(data)
        return

    if not data:
        print_table(["Flow type"], [], title="Flow types")
        return

    # One type per line, easy to pipe.
    for value in data:
        print(value)  # noqa: T201
