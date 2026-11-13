"""Render the server's screen tree from the root, along tree edges.

The shape is the finding: a long unbranching chain means exploration never
escaped a funnel, a wide shallow tree means it never got past the lobby.
"""

from rich.console import Console
from rich.markup import escape
from rich.tree import Tree

from minitest_cli.commands.screens_format import tree_title
from minitest_cli.commands.screens_helpers import TreeIndex, via_markup
from minitest_cli.models import ScreenTransition, TreeScreen

EXPLORED = "explored"


def visible_keys(index: TreeIndex, selected: list[TreeScreen]) -> set[str]:
    """The selected screens plus their ancestors, so a filtered tree keeps its paths."""
    keys: set[str] = set()
    for screen in selected:
        current: TreeScreen | None = screen
        while current is not None and current.screen_key not in keys:
            keys.add(current.screen_key)
            parent = index.parent(current)
            current = index.screens.get(parent.from_screen_key) if parent else None
    return keys


def _screen_label(screen: TreeScreen) -> str:
    bits = [f"[bold]{escape(screen.display_name)}[/bold]"]
    if screen.area:
        bits.append(f"[cyan]({escape(screen.area)})[/cyan]")
    if screen.counts.pending:
        bits.append(f"[yellow]{screen.counts.pending} pending[/yellow]")
    if screen.counts.blocked:
        bits.append(f"[red]{screen.counts.blocked} blocked[/red]")
    return " ".join(bits)


def _cross_link_lines(index: TreeIndex, screen: TreeScreen) -> list[str]:
    """One line per destination reached from here other than by a tree edge."""
    vias: dict[str, list[str]] = {}
    for transition in index.pick(screen.outgoing_transition_ids):
        if transition.status != EXPLORED or transition.is_tree_edge:
            continue
        if transition.to_screen_key is None:
            continue
        labels = vias.setdefault(transition.to_screen_key, [])
        label = via_markup(transition)
        if label not in labels:
            labels.append(label)

    lines: list[str] = []
    for key, labels in vias.items():
        missing = "" if key in index.screens else ", no screen row"
        lines.append(
            f"[dim]↪ {escape(index.name(key))} (also via {', '.join(labels)}{missing})[/dim]"
        )
    return lines


class _Renderer:
    def __init__(self, index: TreeIndex, visible: set[str] | None) -> None:
        self.index = index
        self.visible = visible
        self.seen: set[str] = set()

    def shows(self, screen: TreeScreen) -> bool:
        return self.visible is None or screen.screen_key in self.visible

    def attach(self, parent: Tree, screen: TreeScreen, via: ScreenTransition | None) -> None:
        if screen.screen_key in self.seen:
            return
        self.seen.add(screen.screen_key)
        prefix = f"[dim]{via_markup(via)} →[/dim] " if via else ""
        branch = parent.add(prefix + _screen_label(screen))
        for transition in self.index.pick(screen.child_transition_ids):
            child = self.index.screens.get(transition.to_screen_key or "")
            if child is not None and self.shows(child):
                self.attach(branch, child, transition)
        for line in _cross_link_lines(self.index, screen):
            branch.add(line)


def render_tree(index: TreeIndex, shown: list[TreeScreen], *, filtered: bool) -> None:
    tree = index.tree
    renderer = _Renderer(index, visible_keys(index, shown) if filtered else None)
    output = Tree(tree_title(index, shown))

    root = index.screens.get(tree.root_screen_key or "")
    if root is None:
        output.add("[dim]No root recorded yet — every screen is detached.[/dim]")
    elif renderer.shows(root):
        renderer.attach(output, root, None)

    detached = [
        index.screens[key]
        for key in tree.detached_screen_keys
        if key in index.screens and renderer.shows(index.screens[key])
    ]
    if detached:
        branch = output.add("[bold]Detached[/bold] [dim](not reachable from the root)[/dim]")
        for screen in detached:
            branch.add(_screen_label(screen))

    Console().print(output)
