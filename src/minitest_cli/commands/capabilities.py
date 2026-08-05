"""Print what Mini (the Minitap testing agent) can and cannot do on a platform.

The envelope is served by testing-service so it never drifts from what the
tester agent is actually told at run time: ``GET /api/skills/knowledge`` returns
markdown (``mini-capabilities``) or structured rows (``capabilities``), both
scopable with ``?platform=``.
"""

import asyncio
from typing import Annotated, Any

import httpx
import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.api.errors import format_network_error
from minitest_cli.core.auth import require_auth
from minitest_cli.core.config import Settings
from minitest_cli.utils.output import print_error, print_json

EXIT_NETWORK_ERROR = 3

PLATFORMS = ("android", "ios", "web")

app = typer.Typer(
    name="capabilities",
    help="Show what Mini can and cannot do, scoped to a platform.",
)


def _get_settings() -> Settings:
    return typer.Context.settings  # type: ignore[attr-defined]


def _is_json_mode() -> bool:
    return typer.Context.json_mode  # type: ignore[attr-defined]


def _fetch(settings: Settings, path: str, platform: str | None) -> httpx.Response:
    async def _run() -> httpx.Response:
        async with ApiClient(settings) as client:
            params = {"platform": platform} if platform else None
            return await client.get(f"/api/skills/knowledge{path}", params=params)

    try:
        resp = asyncio.run(_run())
    except httpx.HTTPError as exc:
        print_error(format_network_error(exc))
        raise typer.Exit(code=EXIT_NETWORK_ERROR) from exc

    if resp.status_code >= 400:
        print_error(f"Could not read capabilities ({resp.status_code}): {resp.text}")
        raise typer.Exit(code=EXIT_NETWORK_ERROR)
    return resp


@app.callback(invoke_without_command=True)
def capabilities(
    platform: Annotated[
        str | None,
        typer.Option(
            "--platform",
            help=f"Scope to one platform ({', '.join(PLATFORMS)}). Omit for all.",
        ),
    ] = None,
) -> None:
    """Print Mini's capability envelope for a platform.

    Write acceptance criteria only inside this envelope: a criterion Mini
    cannot physically perform or observe fails as unprocessable, not because
    the app is broken.
    """
    if platform is not None and platform not in PLATFORMS:
        raise typer.BadParameter(f"Platform must be one of: {', '.join(PLATFORMS)}")

    settings = _get_settings()
    require_auth(settings)

    if _is_json_mode():
        payload: Any = _fetch(settings, "/capabilities", platform).json()
        print_json(payload)
        return

    print(_fetch(settings, "/mini-capabilities", platform).text)  # noqa: T201
