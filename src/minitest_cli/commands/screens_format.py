"""Table and hint rendering for ``minitest screens``."""

from minitest_cli.commands.screens_helpers import dangling_edges, parked_count, truncate
from minitest_cli.models import ScreenMapResponse, ScreenNode

BASE_HEADERS = ["Depth", "Screen", "Area", "Reach", "Out", "Parked", "Status"]

_NAME_WIDTH = 44
_REASON_WIDTH = 34


def reach_label(node: ScreenNode) -> str:
    """Summarise what it takes to stand on this screen."""
    ctx = node.context
    if ctx is None:
        return "—"
    parts: list[str] = []
    if ctx.reachable_via:
        parts.append(ctx.reachable_via)
    if ctx.requires_auth:
        parts.append(f"auth:{ctx.persona_ref or '?'}")
    if not ctx.cheaply_reachable:
        parts.append("costly")
    return " ".join(parts) or "—"


def status_label(node: ScreenNode) -> str:
    """Render the blocked reason, which is a reason rather than a boolean."""
    if node.blocked_reason:
        return truncate(node.blocked_reason, _REASON_WIDTH)
    return "ok"


def headers(*, show_platform: bool) -> list[str]:
    if not show_platform:
        return BASE_HEADERS
    return [*BASE_HEADERS[:2], "Platform", *BASE_HEADERS[2:]]


def format_screen_row(node: ScreenNode, *, show_platform: bool) -> list[str]:
    """Format one screen as a table row."""
    parked = parked_count(node)
    row = [
        str(node.depth),
        truncate(node.display_name, _NAME_WIDTH),
        node.area or "—",
        reach_label(node),
        str(len(node.outgoing) - parked),
        str(parked) if parked else "—",
        status_label(node),
    ]
    if show_platform:
        row.insert(2, node.platform)
    return row


def table_title(screen_map: ScreenMapResponse, shown: list[ScreenNode]) -> str:
    """Title that distinguishes 'filtered down to' from 'this is all there is'."""
    total = screen_map.screen_count
    scope = f"{len(shown)} of {total}" if len(shown) != total else str(total)
    suffix = f" ({screen_map.platform})" if screen_map.platform else ""
    depths = [n.depth for n in shown]
    span = f", depth {min(depths)}–{max(depths)}" if depths else ""
    return f"Screens{suffix} — {scope} mapped{span}"


def frontier_hint(shown: list[ScreenNode], all_nodes: list[ScreenNode]) -> str:
    """Surface the frontier — the question a screen list is usually asked to answer.

    ``shown`` drives the counts the user can see; ``all_nodes`` drives the
    dangling check, so a filtered view never reports its own filtering as a
    broken map.
    """
    parked = sum(parked_count(n) for n in shown)
    blocked = sum(1 for n in shown if n.blocked_reason)
    dangling = len(dangling_edges(all_nodes))

    bits: list[str] = []
    if parked:
        bits.append(f"{parked} parked edge(s) — onward navigation seen but not followed")
    if blocked:
        bits.append(f"{blocked} blocked screen(s)")
    if dangling:
        bits.append(f"{dangling} edge(s) leading to a screen with no row in the map")
    if not bits:
        return ""
    return f"Frontier: {'; '.join(bits)}. Use --tree to see where they sit."


def empty_message(screen_map: ScreenMapResponse, *, area: str | None, blocked: bool) -> str:
    """Explain an empty result: nothing crawled yet, versus filtered to nothing."""
    if screen_map.screen_count == 0:
        return (
            "No screens mapped for this app yet. The map is written by the exploration "
            "crawl as it walks a build, so it stays empty until a crawl has run."
        )
    filters: list[str] = []
    if area is not None:
        filters.append(f"--area {area}")
    if blocked:
        filters.append("--blocked")
    applied = " ".join(filters) or "the current filters"
    return f"{screen_map.screen_count} screen(s) mapped, but none match {applied}."
