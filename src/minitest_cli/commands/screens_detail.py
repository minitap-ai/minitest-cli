"""Human-readable rendering for ``minitest screens get``."""

from rich.console import Console
from rich.markup import escape
from rich.table import Table

from minitest_cli.commands.screens_helpers import TreeIndex, account_label, element_label
from minitest_cli.models import ScreenContext, ScreenTransition, TreeScreen

_STATUS_ORDER = ["pending", "blocked", "skipped", "explored"]
_STATUS_STYLE = {"pending": "yellow", "blocked": "red", "skipped": "dim", "explored": "green"}


def _context_lines(ctx: ScreenContext | None) -> list[str]:
    if ctx is None:
        return ["  [dim]No context recorded for this screen.[/dim]"]

    lines = [f"  Reachable via : {escape(ctx.reachable_via or '—')}"]
    if ctx.deeplink_uri:
        lines.append(f"  Deeplink      : {escape(ctx.deeplink_uri)}")
    lines.append(f"  Requires auth : {'yes' if ctx.requires_auth else 'no'}")
    if ctx.requires_auth:
        lines.append(
            f"  As persona    : {escape(ctx.persona_ref or '') or '[red]unspecified[/red]'}"
        )
    if ctx.cheaply_reachable:
        lines.append("  Cheap to reach: yes")
    else:
        reason = escape(ctx.cheaply_reachable_reason or "")
        lines.append(f"  Cheap to reach: [yellow]no[/yellow] — {reason}")
    if ctx.preconditions:
        rendered = ", ".join(f"{p.kind}({p.ref})" if p.ref else p.kind for p in ctx.preconditions)
        lines.append(f"  Preconditions : {escape(rendered)}")
    else:
        lines.append("  Preconditions : none needed")
    return lines


def _identity_lines(screen: TreeScreen) -> list[str]:
    depth = "— (detached: not reachable from the root)" if screen.depth is None else screen.depth
    lines = [
        f"  Key           : {escape(screen.screen_key)}",
        f"  Depth         : {depth}",
        f"  Area          : {escape(screen.area or '—')}",
    ]
    if screen.first_reached_at:
        lines.append(f"  First reached : {screen.first_reached_at:%Y-%m-%d %H:%M}")
    if screen.notes:
        lines.append(f"  Notes         : {escape(screen.notes)}")
    if screen.screenshot_url:
        lines.append(f"  Screenshot    : {escape(screen.screenshot_url)}")
    elif screen.screenshot_path:
        lines.append(f"  Screenshot    : [dim]{escape(screen.screenshot_path)} (unsigned)[/dim]")
    return lines


def _walk_line(label: str, t: ScreenTransition) -> str:
    return f"  {label} [dim]({escape(account_label(t))})[/dim]"


def _reached_from_lines(index: TreeIndex, screen: TreeScreen) -> list[str]:
    lines: list[str] = []
    for t in index.pick(screen.incoming_transition_ids):
        via = f"{escape(index.name(t.from_screen_key))} via {escape(element_label(t))}"
        parent = " [green](parent)[/green]" if t.id == screen.parent_transition_id else ""
        lines.append(_walk_line(via, t) + parent)
    if lines:
        return lines
    if screen.depth == 0:
        return ["  [dim]Nothing — this is the root.[/dim]"]
    return ["  [dim]Nothing — no explored transition leads here.[/dim]"]


def _children_lines(index: TreeIndex, screen: TreeScreen) -> list[str]:
    lines = [
        _walk_line(f"{escape(element_label(t))} → {escape(index.name(t.to_screen_key))}", t)
        for t in index.pick(screen.child_transition_ids)
    ]
    return lines or ["  [dim]None — no screen is placed under this one.[/dim]"]


def _detail(index: TreeIndex, t: ScreenTransition) -> str:
    if t.status == "explored":
        return f"→ {escape(index.name(t.to_screen_key))}"
    detail = escape(t.reason or "")
    if t.gated_by:
        detail += f" [dim](gated by ask {escape(t.gated_by)})[/dim]"
    return detail


def _elements_table(index: TreeIndex, screen: TreeScreen) -> Table:
    outgoing = index.pick(screen.outgoing_transition_ids)
    rank = {status: i for i, status in enumerate(_STATUS_ORDER)}
    outgoing.sort(key=lambda t: rank.get(t.status, len(rank)))

    table = Table(title=f"Elements on {escape(screen.display_name)}", header_style="bold")
    for header in ("Status", "Element", "Kind", "Account", "Detail"):
        table.add_column(header)
    for t in outgoing:
        style = _STATUS_STYLE.get(t.status, "")
        table.add_row(
            f"[{style}]{escape(t.status)}[/{style}]" if style else escape(t.status),
            escape(element_label(t)),
            escape(t.element_kind),
            escape(account_label(t)),
            _detail(index, t),
        )
    return table


def render_screen(index: TreeIndex, screen: TreeScreen) -> None:
    """Print one screen: identity, how to stand on it, how it is reached, what it leads to."""
    console = Console()
    platform = escape(index.tree.platform)
    console.print(f"[bold]{escape(screen.display_name)}[/bold]  [dim]({platform})[/dim]")
    for section, lines in (
        ("", _identity_lines(screen)),
        ("Context — what it takes to stand here", _context_lines(screen.context)),
        ("Reached from", _reached_from_lines(index, screen)),
        ("Children", _children_lines(index, screen)),
    ):
        if section:
            console.print(f"\n[bold]{section}[/bold]")
        for line in lines:
            console.print(line)

    if not screen.outgoing_transition_ids:
        console.print("\n[dim]No elements recorded on this screen.[/dim]")
        return
    console.print()
    console.print(_elements_table(index, screen))
