"""Render the screen map as a navigation tree.

The tree is the view that answers "where did the crawl actually go", because
the shape is the finding: a long unbranching chain means exploration never
escaped a funnel, while a wide shallow tree means it never got past the lobby.
"""

from rich.console import Console
from rich.tree import Tree

from minitest_cli.commands.screens_helpers import truncate
from minitest_cli.models import ScreenNode

_ACTION_WIDTH = 46


def _label(node: ScreenNode, via: str | None) -> str:
    bits: list[str] = []
    if via:
        bits.append(f"[dim]{truncate(via, _ACTION_WIDTH)} →[/dim]")
    bits.append(f"[bold]{node.display_name}[/bold]")
    if node.area:
        bits.append(f"[cyan]({node.area})[/cyan]")
    if node.blocked_reason:
        bits.append(f"[red]blocked: {truncate(node.blocked_reason, _ACTION_WIDTH)}[/red]")
    return " ".join(bits)


def _attach(
    parent: Tree,
    node: ScreenNode,
    by_key: dict[str, ScreenNode],
    seen: set[str],
    via: str | None,
) -> None:
    if node.screen_key in seen:
        # A cycle, or a screen reachable two ways. Mark it and stop, so the
        # tree stays finite and nothing is silently duplicated.
        parent.add(f"[dim]{via + ' → ' if via else ''}{node.display_name} ↩ (shown above)[/dim]")
        return
    seen.add(node.screen_key)

    branch = parent.add(_label(node, via))
    for edge in node.outgoing:
        if edge.parked:
            reason = edge.parked_reason or "no reason given"
            branch.add(
                f"[yellow]⇢ {truncate(edge.action, _ACTION_WIDTH)}[/yellow] "
                f"[dim](parked: {truncate(reason, _ACTION_WIDTH)})[/dim]"
            )
            continue
        child = by_key.get(edge.to_screen_key or "")
        if child is None:
            branch.add(
                f"[dim]{truncate(edge.action, _ACTION_WIDTH)} → "
                f"{edge.to_screen_key or '?'} (not in this view)[/dim]"
            )
            continue
        _attach(branch, child, by_key, seen, edge.action)


def render_tree(nodes: list[ScreenNode], *, title: str) -> None:
    """Print the map as a tree rooted at whatever nothing else navigates to."""
    by_key = {n.screen_key: n for n in nodes}
    entered = {
        edge.to_screen_key
        for n in nodes
        for edge in n.outgoing
        if edge.to_screen_key and not edge.parked
    }
    roots = [n for n in nodes if n.screen_key not in entered]
    if not roots:
        # Every node is entered by some edge (a fully cyclic map). Fall back to
        # the shallowest node so the tree still has somewhere to start.
        roots = sorted(nodes, key=lambda n: (n.depth, n.discovered_at))[:1]

    tree = Tree(title)
    seen: set[str] = set()
    for root in sorted(roots, key=lambda n: (n.depth, n.discovered_at)):
        _attach(tree, root, by_key, seen, None)

    # Anything the walk never reached (e.g. filtered-out parents) still belongs
    # in the output — dropping it would understate the map.
    for node in nodes:
        if node.screen_key not in seen:
            _attach(tree, node, by_key, seen, None)

    Console().print(tree)
