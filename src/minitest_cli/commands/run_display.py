"""Display and formatting helpers for run commands."""

import math

from minitest_cli.models.story_run import PlatformRun, StoryRunListResponse, StoryRunResponse
from minitest_cli.models.targets import target_label
from minitest_cli.utils.output import (
    err_console,
    print_error,
    print_info,
    print_json,
    print_success,
    print_table,
)

RUN_TABLE_HEADERS = ["ID", "User Story", "Status", "Created"]

RESULTS_TABLE_HEADERS = ["Criterion ID", "Platform", "Result", "Fail Reason"]


_TERMINAL_EXEC_STATES = {"completed", "failed", "skipped"}


def _derive_run_status(run: StoryRunResponse) -> str:
    """Collapse the per-platform ``platforms[]`` array to a coarse run status.

    Mirrors the heuristic used by the cockpit / webapp: any platform
    with a stamped ``cancellation_requested_at`` short-circuits to
    ``cancelled``; otherwise we pick the worst platform state in
    lifecycle order (running > pending/blocked > failed > completed).
    """
    if any(p.cancellation_requested_at is not None for p in run.platforms):
        return "cancelled"
    states = [p.execution_state for p in run.platforms]
    if not states:
        return "pending"
    if "running" in states:
        return "running"
    if "pending" in states or "blocked" in states:
        return "pending"
    if "failed" in states:
        return "failed"
    if all(s in _TERMINAL_EXEC_STATES for s in states) and any(s == "completed" for s in states):
        return "completed"
    return "pending"


def format_run_row(run: StoryRunResponse) -> list[str]:
    """Format a single StoryRunResponse as a table row."""
    return [
        run.id,
        run.user_story_name or run.user_story_id,
        _derive_run_status(run),
        run.created_at.strftime("%Y-%m-%d %H:%M"),
    ]


def _platform_label(p: PlatformRun) -> str:
    return p.label or target_label(p.platform, p.browser, p.viewport)


def _platform_status_line(p: PlatformRun) -> tuple[str, str | None]:
    """Build a status line for a per-platform child."""
    parts: list[str] = [f"  {_platform_label(p)}:"]
    if p.error_message:
        parts.append(f" [bold red]error — {p.error_message}[/bold red]")
    elif p.recording_url:
        parts.append(" [bold green]done[/bold green]")
    else:
        parts.append(" [dim]pending[/dim]")
    return "".join(parts), p.recording_url


def display_run_result(run: StoryRunResponse, json_mode: bool) -> None:
    """Display the full results of a completed run."""
    if json_mode:
        print_json(run.model_dump(mode="json", by_alias=True))
        return

    status = _derive_run_status(run)
    status_icon = {
        "completed": "✓",
        "failed": "✗",
        "pending": "…",
        "running": "…",
        "cancelled": "⊘",
    }.get(status, "?")
    print_info(f"Run {run.id} — {status_icon} {status}")

    for p in run.platforms:
        line, recording = _platform_status_line(p)
        err_console.print(line)
        if recording:
            err_console.print(f"    Recording: {recording}")

    rows: list[list[str]] = []
    for cr in run.results:
        result_str = "[green]✓ pass[/green]" if cr.success else "[red]✗ fail[/red]"
        platform_label = target_label(cr.platform, None, None)
        if cr.is_platform_override:
            platform_label += " *"
        rows.append([cr.criterion_version_id, platform_label, result_str, cr.fail_reason or ""])

    if rows:
        print_table(RESULTS_TABLE_HEADERS, rows, title="Acceptance Criteria Results")

    if status == "completed":
        all_passed = all(cr.success for cr in run.results)
        if run.results and all_passed:
            print_success("All acceptance criteria passed.")
        elif run.results:
            print_error("Some acceptance criteria failed.")
    elif status == "failed":
        errors = [
            f"{_platform_label(p)}: {p.error_message}" for p in run.platforms if p.error_message
        ]
        if errors:
            print_error(f"Run failed — {'; '.join(errors)}")
        else:
            print_error("Run failed.")
    elif status == "cancelled":
        print_info("Run cancelled.")


def format_run_pagination_info(data: StoryRunListResponse) -> tuple[str, str]:
    """Return (title, tip) for paginated run table display."""
    total_pages = math.ceil(data.total / data.page_size) if data.total else 1
    start = (data.page - 1) * data.page_size + 1
    end = min(data.page * data.page_size, data.total)
    title = f"Runs — page {data.page} of {total_pages}, showing {start}–{end} of {data.total}"

    tip = ""
    if data.page < total_pages:
        tip = f"Use --page {data.page + 1} to see next page, or --all to fetch everything."
    return title, tip
