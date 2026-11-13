"""Table, title and summary rendering for ``minitest screens list``."""

from rich.markup import escape

from minitest_cli.commands.screens_helpers import TreeIndex, element_label, truncate
from minitest_cli.models import ScreenTree, ScreenTreeResponse, TreeScreen

HEADERS = ["Depth", "Screen", "Area", "Reached via", "Explored", "Pending", "Blocked", "Skipped"]

_NAME_WIDTH = 44
_VIA_WIDTH = 30


def reached_via(index: TreeIndex, screen: TreeScreen) -> str:
    parent = index.parent(screen)
    if parent is None:
        return "—"
    return escape(truncate(element_label(parent), _VIA_WIDTH))


def format_screen_row(index: TreeIndex, screen: TreeScreen) -> list[str]:
    counts = screen.counts
    return [
        "—" if screen.depth is None else str(screen.depth),
        escape(truncate(screen.display_name, _NAME_WIDTH)),
        escape(screen.area or "—"),
        reached_via(index, screen),
        str(counts.explored),
        str(counts.pending),
        str(counts.blocked),
        str(counts.skipped),
    ]


def tree_title(index: TreeIndex, shown: list[TreeScreen]) -> str:
    tree = index.tree
    total = len(tree.screens)
    scope = f"{len(shown)} of {total}" if len(shown) != total else str(total)
    root = index.name(tree.root_screen_key) if tree.root_screen_key else "none recorded"
    return f"Screens ({tree.platform}) — {scope} screen(s), root: {escape(root)}"


def summary_line(tree: ScreenTree, shown: list[TreeScreen]) -> str:
    """Totals over the shown screens: their outgoing transitions by status, and detached."""
    detached = set(tree.detached_screen_keys)
    parts = [
        f"{len(shown)} screen(s)",
        f"{sum(s.counts.explored for s in shown)} explored",
        f"{sum(s.counts.pending for s in shown)} pending",
        f"{sum(s.counts.blocked for s in shown)} blocked",
        f"{sum(s.counts.skipped for s in shown)} skipped",
        f"{sum(1 for s in shown if s.screen_key in detached)} detached",
    ]
    return "Totals: " + " · ".join(parts)


def empty_message(response: ScreenTreeResponse, *, area: str | None, blocked: bool) -> str:
    """Explain an empty result: nothing crawled yet, versus filtered to nothing."""
    total = sum(len(tree.screens) for tree in response.trees)
    if total == 0:
        return (
            "No screens mapped for this app yet. The tree is written by the exploration "
            "crawl as it walks a build, so it stays empty until a crawl has run."
        )
    filters: list[str] = []
    if area is not None:
        filters.append(f"--area {area}")
    if blocked:
        filters.append("--blocked")
    return f"{total} screen(s) mapped, but none match {' '.join(filters)}."
