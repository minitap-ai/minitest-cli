"""Human-readable rendering for ``minitest screens get``."""

from minitest_cli.models import ScreenNode
from minitest_cli.utils.output import err_console, print_info, print_table

_EDGE_HEADERS = ["Action", "Leads to", "State"]


def _context_lines(node: ScreenNode) -> list[str]:
    ctx = node.context
    if ctx is None:
        return ["  [dim]No context recorded for this screen.[/dim]"]

    lines = [f"  Reachable via : {ctx.reachable_via or '—'}"]
    if ctx.deeplink_uri:
        lines.append(f"  Deeplink      : {ctx.deeplink_uri}")
    lines.append(f"  Requires auth : {'yes' if ctx.requires_auth else 'no'}")
    if ctx.requires_auth:
        lines.append(f"  As persona    : {ctx.persona_ref or '[red]unspecified[/red]'}")
    if ctx.cheaply_reachable:
        lines.append("  Cheap to reach: yes")
    else:
        lines.append(f"  Cheap to reach: [yellow]no[/yellow] — {ctx.cheaply_reachable_reason}")
    if ctx.preconditions:
        rendered = ", ".join(f"{p.kind}({p.ref})" if p.ref else p.kind for p in ctx.preconditions)
        lines.append(f"  Preconditions : {rendered}")
    else:
        lines.append("  Preconditions : none needed")
    return lines


def _edge_rows(node: ScreenNode) -> list[list[str]]:
    rows: list[list[str]] = []
    for edge in node.outgoing:
        if edge.parked:
            state = f"parked ({edge.parked_kind or 'unclassified'}): {edge.parked_reason}"
            destination = "— not entered"
        else:
            state = "followed"
            if edge.consecutive_failures:
                state = f"followed, {edge.consecutive_failures} consecutive failure(s)"
            destination = edge.to_screen_key or "?"
        rows.append([edge.action, destination, state])
    return rows


def render_screen(node: ScreenNode) -> None:
    """Print one screen: what it is, how to stand on it, and where it leads."""
    err_console.print(f"[bold]{node.display_name}[/bold]  [dim]({node.platform})[/dim]")
    err_console.print(f"  Key           : {node.screen_key}")
    err_console.print(f"  Depth         : {node.depth}")
    err_console.print(f"  Area          : {node.area or '—'}")
    err_console.print(f"  First reached : {node.first_reached_at:%Y-%m-%d %H:%M}")
    if node.blocked_reason:
        err_console.print(f"  [red]Blocked[/red]       : {node.blocked_reason}")
        if node.gated_by:
            err_console.print(f"  Gated by ask  : {node.gated_by}")
    if node.screenshot_url:
        err_console.print(f"  Screenshot    : {node.screenshot_url}")
    elif node.screenshot_path:
        err_console.print(f"  Screenshot    : [dim]{node.screenshot_path} (unsigned)[/dim]")

    err_console.print("\n[bold]Context[/bold] — what it takes to stand here")
    for line in _context_lines(node):
        err_console.print(line)

    rows = _edge_rows(node)
    if not rows:
        print_info("\nNo outgoing edges recorded — the crawl saw no way onward from here.")
        return
    print_table(_EDGE_HEADERS, rows, title=f"Outgoing from {node.display_name}")
