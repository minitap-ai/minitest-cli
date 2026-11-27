"""One-line renderings of a PR check's plan, results and counts."""

from typing import Any

from rich.markup import escape

from minitest_cli.utils.output import CliConsole

# Never wrapped: a folded report URL or annotation is useless in a CI log.
console = CliConsole(stderr=True, highlight=False, soft_wrap=True)


def warn(message: str) -> None:
    console.print(f"[bold yellow]Warning:[/bold yellow] {escape(message)}")


def info(message: str) -> None:
    console.print(f"[dim]{escape(message)}[/dim]")


def error(message: str) -> None:
    console.print(f"[bold red]Error:[/bold red] {escape(message)}")


VERDICT_STYLES = {
    "passed": ("✓", "green"),
    "warning": ("!", "yellow"),
    "critical": ("✗", "red"),
    "known": ("~", "blue"),
    "not_tested": ("-", "dim"),
    "errored": ("✗", "magenta"),
}
SEEN_CHARS = 120
COUNT_ORDER = ("passed", "warning", "critical", "known", "not_tested", "errored")


def one_line(text: str, limit: int = SEEN_CHARS) -> str:
    """Mini's account of a result, cut to one short line: the report holds the rest."""
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


def timestamp(seconds: float | int | None) -> str:
    if seconds is None:
        return ""
    total = int(seconds)
    return f" @ {total // 60}:{total % 60:02d}"


def plan_lines(checks: list[dict[str, Any]]) -> list[str]:
    groups = [c.get("group") for c in checks]
    head = (
        f"Plan: {len(checks)} check(s) ({groups.count('change')} change,"
        f" {groups.count('impact')} impact)"
    )
    lines = [head]
    for check in checks:
        why = f" [dim]— {escape(str(check['why']))}[/dim]" if check.get("why") else ""
        lines.append(f"  · {check.get('group', '?'):<6} {escape(str(check.get('label')))}{why}")
    return lines


def item_line(item: dict[str, Any], label: str) -> str:
    verdict = str(item.get("verdict"))
    mark, style = VERDICT_STYLES.get(verdict, ("?", "white"))
    platform = f"[{item.get('platform')}]"
    head = f"[{style}]{mark} {escape(f'{platform:<10}')} {verdict:<10}[/{style}] {escape(label)}"
    shows_seen = item.get("seen") and verdict not in ("passed", "known")
    seen = f" — {escape(one_line(str(item['seen'])))}" if shows_seen else ""
    carried = " [dim](carried)[/dim]" if item.get("tag") == "carried" else ""
    return f"{head}{timestamp(item.get('at'))}{seen}{carried}"


def counts_line(counts: dict[str, dict[str, int]] | None) -> str:
    parts = []
    for platform, by_verdict in (counts or {}).items():
        shown = [f"{by_verdict[v]} {v}" for v in COUNT_ORDER if by_verdict.get(v)]
        parts.append(f"{platform}: {', '.join(shown) or 'nothing verified'}")
    return " · ".join(parts) or "no results"


def gha_escape(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def gha_property(text: str) -> str:
    return gha_escape(text).replace(":", "%3A").replace(",", "%2C")


def critical_annotations(report: dict[str, Any]) -> list[str]:
    """One ``::error::`` workflow command per critical check and platform."""
    lines = []
    for check in report.get("checks") or []:
        for platform, result in (check.get("platforms") or {}).items():
            if result and result.get("verdict") == "critical":
                title = gha_property(f"{check.get('label')} ({platform})")
                body = gha_escape(one_line(str(result.get("seen") or check.get("expected") or "")))
                lines.append(f"::error title={title}::{body}")
    return lines
