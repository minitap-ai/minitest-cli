import asyncio
from typing import Annotated

import httpx
import typer

from minitest_cli.api.errors import format_network_error
from minitest_cli.commands.apps_helpers import get_app_request
from minitest_cli.commands.env_helpers import resolve_app_and_tenant
from minitest_cli.core.auth import require_auth
from minitest_cli.models.app import AppDetailResponse
from minitest_cli.utils.output import print_error, print_json

EXIT_NETWORK_ERROR = 3


def get_app(
    app_id: Annotated[str, typer.Argument(help="App ID.")],
) -> None:
    settings = typer.Context.settings  # type: ignore[attr-defined]
    json_mode = typer.Context.json_mode  # type: ignore[attr-defined]
    require_auth(settings)

    async def _run() -> AppDetailResponse:
        resolved_app_id, tenant_id = await resolve_app_and_tenant(settings, app_id)
        return await get_app_request(
            settings,
            tenant_id=tenant_id,
            app_id=resolved_app_id,
        )

    try:
        detail = asyncio.run(_run())
    except httpx.HTTPError as exc:
        print_error(format_network_error(exc))
        raise typer.Exit(code=EXIT_NETWORK_ERROR) from exc

    payload = detail.model_dump(mode="json", by_alias=True)
    if json_mode:
        print_json(payload)
        return
    for key, value in payload.items():
        print(f"{key}: {'-' if value is None else value}")  # noqa: T201
