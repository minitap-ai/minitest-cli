"""Data access and selection for ``minitest screens``.

Presentation (table headers, rows, hint lines) lives in ``screens_format``.
"""

from minitest_cli.api.client import ApiClient
from minitest_cli.commands._response_errors import handle_response_error
from minitest_cli.commands.build_helpers import run_api_call
from minitest_cli.core.config import Settings
from minitest_cli.models import ScreenEdge, ScreenMapResponse, ScreenNode


def screens_path(app_id: str) -> str:
    """Return the screen-map API path for an app."""
    return f"/api/v1/apps/{app_id}/screens"


async def _get_screen_map(
    settings: Settings, app_id: str, platform: str | None
) -> ScreenMapResponse:
    params: dict[str, str] = {}
    if platform is not None:
        params["platform"] = platform

    async with ApiClient(settings) as client:
        resp = await client.get(screens_path(app_id), params=params)
    handle_response_error(resp, resource="Screen map")
    return ScreenMapResponse.model_validate(resp.json())


def fetch_screen_map(settings: Settings, app_id: str, platform: str | None) -> ScreenMapResponse:
    """Fetch the whole screen map in one call."""
    return run_api_call(_get_screen_map(settings, app_id, platform))


def truncate(text: str, limit: int) -> str:
    """Shorten text for display, marking the cut."""
    return text if len(text) <= limit else text[: limit - 1] + "…"


def filter_nodes(
    nodes: list[ScreenNode], *, area: str | None, blocked_only: bool
) -> list[ScreenNode]:
    """Apply the client-side filters. The API returns the whole map in one fetch."""
    selected = nodes
    if area is not None:
        wanted = area.strip().casefold()
        selected = [n for n in selected if (n.area or "").casefold() == wanted]
    if blocked_only:
        selected = [n for n in selected if n.blocked_reason]
    return selected


def find_node(nodes: list[ScreenNode], needle: str) -> list[ScreenNode]:
    """Match a screen by canonical key or display name, case-insensitively.

    Returns every match: one screen key can exist on both platforms, and the
    caller needs to say so rather than silently picking one.
    """
    wanted = " ".join(needle.split()).casefold()
    return [
        n for n in nodes if n.screen_key.casefold() == wanted or n.display_name.casefold() == wanted
    ]


def parked_count(node: ScreenNode) -> int:
    """Edges the crawl saw but chose not to follow."""
    return sum(1 for edge in node.outgoing if edge.parked)


def dangling_edges(nodes: list[ScreenNode]) -> list[tuple[ScreenNode, ScreenEdge]]:
    """Followed edges whose destination has no row in the map.

    The crawl says it walked somewhere, but no screen was ever written under
    that key — usually because the destination was named slightly differently
    than the screen later called itself, so the two normalise apart. It means
    the map understates what was actually reached, which is worth saying out
    loud rather than rendering as a silently truncated tree.
    """
    keys = {n.screen_key for n in nodes}
    return [
        (node, edge)
        for node in nodes
        for edge in node.outgoing
        if not edge.parked and (edge.to_screen_key or "") not in keys
    ]
