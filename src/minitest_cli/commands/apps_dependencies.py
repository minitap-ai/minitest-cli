"""'apps dependencies' subcommand: render user-story dependency graph."""

import asyncio
from typing import Annotated, Any

import httpx
import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.core.app_context import resolve_app_id
from minitest_cli.core.auth import require_auth
from minitest_cli.core.config import Settings
from minitest_cli.utils.mermaid import build_dependency_graph
from minitest_cli.utils.output import print_error, print_info, print_json

EXIT_NETWORK_ERROR = 3


def _get_settings() -> Settings:
    return typer.Context.settings  # type: ignore[attr-defined]


def _is_json_mode() -> bool:
    return typer.Context.json_mode  # type: ignore[attr-defined]


def _get_app_flag() -> str | None:
    return typer.Context.app_flag  # type: ignore[attr-defined]


def dependencies(
    app_id_arg: Annotated[
        str | None,
        typer.Argument(help="App ID. Falls back to --app / MINITEST_APP_ID if omitted."),
    ] = None,
) -> None:
    """Print the user-story dependency graph as a Mermaid flowchart.

    Fetches the dependency graph for the app and renders it as a Mermaid
    ``flowchart TD`` diagram to stdout. With ``--json``, outputs the raw
    graph data instead.
    """
    settings = _get_settings()
    json_mode = _is_json_mode()
    require_auth(settings)
    target = app_id_arg or resolve_app_id(settings, _get_app_flag())

    async def _fetch() -> dict[str, Any]:
        async with ApiClient(settings) as client:
            resp = await client.get(
                f"/api/v1/apps/{target}/user-stories/dependency-graph",
            )
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
            return resp.json()

    try:
        graph = asyncio.run(_fetch())
    except httpx.HTTPError as exc:
        print_error(f"Network error: {exc}")
        raise typer.Exit(code=EXIT_NETWORK_ERROR) from exc

    nodes: list[dict[str, Any]] = graph.get("nodes", [])
    edges: list[dict[str, Any]] = graph.get("edges", [])

    if json_mode:
        print_json(graph)
        return

    mermaid = build_dependency_graph(nodes, edges)
    if not mermaid:
        print_info("No user stories found for this app.")
        raise typer.Exit(code=0)

    print(mermaid)  # noqa: T201
