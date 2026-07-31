"""Read the screen map the exploration crawl built for an app.

Deliberately **read-only**. The crawl writes screens in-process on the
testing-service side, so there is no CLI write surface to build — a write
command here would be speculative API nobody calls.

What this does earn its keep for is looking at the map: confirming an
end-to-end run against a real build actually populated it, and seeing which
nodes are blocked and why, without needing the webapp.
"""

import asyncio
from typing import Annotated, Any

import httpx
import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.core.auth import require_auth
from minitest_cli.core.config import Settings
from minitest_cli.utils.output import output, print_error

EXIT_GENERAL_ERROR = 1
EXIT_NETWORK_ERROR = 3
EXIT_NOT_FOUND = 4

PLATFORMS = ("android", "ios")

app = typer.Typer(name="screens", help="Read an app's crawled screen map.")


@app.callback()
def _callback() -> None:
    """Screen-map operations."""


def _get_settings() -> Settings:
    return typer.Context.settings  # type: ignore[attr-defined]


def _is_json_mode() -> bool:
    return typer.Context.json_mode  # type: ignore[attr-defined]


def _fetch_screen_map(settings: Settings, app_id: str, platform: str | None) -> dict[str, Any]:
    async def _run() -> httpx.Response:
        async with ApiClient(settings) as client:
            params = {"platform": platform} if platform else None
            return await client.get(f"/api/v1/apps/{app_id}/screens", params=params)

    try:
        resp = asyncio.run(_run())
    except httpx.HTTPError as exc:
        print_error(f"Network error: {exc}")
        raise typer.Exit(code=EXIT_NETWORK_ERROR) from exc

    if resp.status_code == 404:
        print_error(f"App not found: {app_id}")
        raise typer.Exit(code=EXIT_NOT_FOUND)
    if resp.status_code in (401, 403):
        print_error(f"Authentication failed ({resp.status_code}).")
        raise typer.Exit(code=EXIT_GENERAL_ERROR)
    if resp.status_code >= 400:
        print_error(f"Could not read the screen map ({resp.status_code}): {resp.text}")
        raise typer.Exit(code=EXIT_NETWORK_ERROR)

    payload = resp.json()
    if not isinstance(payload, dict):
        print_error("Unexpected response shape from the screens endpoint.")
        raise typer.Exit(code=EXIT_NETWORK_ERROR)
    return payload


def _summarise(screen: dict[str, Any]) -> dict[str, str]:
    """One table row per node — the shape a human scans, not the full record.

    ``--json`` gives the complete record; this is the at-a-glance view, so it
    surfaces the questions someone actually asks of a map: how deep is it, what
    is blocked, and where does the crawl stop.
    """
    edges = screen.get("outgoing") or []
    parked = [edge for edge in edges if edge.get("parked")]
    return {
        "depth": str(screen.get("depth", "")),
        "screen": str(screen.get("displayName") or screen.get("screenKey") or ""),
        "key": str(screen.get("screenKey") or ""),
        "area": str(screen.get("area") or "-"),
        "edges": str(len(edges)),
        "parked": str(len(parked)),
        # A reason, never a boolean — the point is that it reads as a sentence.
        "blocked": str(screen.get("blockedReason") or "-"),
    }


@app.command(name="list")
def list_screens(
    app_id: Annotated[
        str,
        typer.Option("--app", help="App ID to read the screen map for. Required."),
    ],
    platform: Annotated[
        str | None,
        typer.Option("--platform", help=f"Restrict to one of: {', '.join(PLATFORMS)}."),
    ] = None,
) -> None:
    """List the screens the crawl reached for an app.

    Without ``--json``, prints a table of one row per screen ordered
    shallowest-first. With ``--json``, prints the full map record including
    each node's ``context``, ``outgoing`` edges and signed screenshot URL.
    """
    settings = _get_settings()
    json_mode = _is_json_mode()
    require_auth(settings)

    if platform is not None and platform not in PLATFORMS:
        print_error(f"Unknown platform '{platform}'. Expected one of: {', '.join(PLATFORMS)}.")
        raise typer.Exit(code=EXIT_GENERAL_ERROR)

    payload = _fetch_screen_map(settings, app_id, platform)

    if json_mode:
        output(payload, json_mode=True)
        return

    screens = payload.get("screens") or []
    if not screens:
        print_error("No screens have been mapped for this app yet.")
        raise typer.Exit(code=EXIT_NOT_FOUND)

    output(
        [_summarise(screen) for screen in screens],
        json_mode=False,
        headers=["depth", "screen", "key", "area", "edges", "parked", "blocked"],
    )
