"""Display and formatting helpers for run commands."""

import math

from minitest_cli.models.story_run import RunStatus, StoryRunListResponse, StoryRunResponse
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


def format_run_row(run: StoryRunResponse) -> list[str]:
    """Format a single StoryRunResponse as a table row."""
    return [
        run.id,
        run.user_story_name or run.user_story_id,
        run.status.value,
        run.created_at.strftime("%Y-%m-%d %H:%M"),
    ]


def _platform_status_line(platform: str, run: StoryRunResponse) -> tuple[str, str | None] | None:
    """Build a status line for a platform from the flat run fields."""
    if platform == "ios" and not run.ios_build_id:
        return None
    if platform == "android" and not run.android_build_id:
        return None

    error = run.ios_error_message if platform == "ios" else run.android_error_message
    recording = run.ios_recording_url if platform == "ios" else run.android_recording_url

    parts: list[str] = [f"  {platform}:"]
    if error:
        parts.append(f" [bold red]error — {error}[/bold red]")
    elif recording:
        parts.append(" [bold green]done[/bold green]")
    else:
        parts.append(" [dim]pending[/dim]")

    return "".join(parts), recording


def display_run_result(run: StoryRunResponse, json_mode: bool) -> None:
    """Display the full results of a completed run."""
    if json_mode:
        print_json(run.model_dump(mode="json"))
        return

    status_icon = {
        RunStatus.completed: "✓",
        RunStatus.failed: "✗",
        RunStatus.pending: "…",
        RunStatus.running: "…",
        RunStatus.cancelled: "⊘",
    }[run.status]
    print_info(f"Run {run.id} — {status_icon} {run.status.value}")

    for platform in ("ios", "android"):
        result = _platform_status_line(platform, run)
        if result is None:
            continue
        line, recording = result
        err_console.print(line)
        if recording:
            err_console.print(f"    Recording: {recording}")

    rows: list[list[str]] = []
    for cr in run.results:
        result_str = "[green]✓ pass[/green]" if cr.success else "[red]✗ fail[/red]"
        rows.append([cr.criterion_version_id, cr.platform, result_str, cr.fail_reason or ""])

    if rows:
        print_table(RESULTS_TABLE_HEADERS, rows, title="Acceptance Criteria Results")

    if run.status == RunStatus.completed:
        all_passed = all(cr.success for cr in run.results)
        if run.results and all_passed:
            print_success("All acceptance criteria passed.")
        elif run.results:
            print_error("Some acceptance criteria failed.")
    elif run.status == RunStatus.failed:
        errors = []
        if run.ios_error_message:
            errors.append(f"iOS: {run.ios_error_message}")
        if run.android_error_message:
            errors.append(f"Android: {run.android_error_message}")
        if errors:
            print_error(f"Run failed — {'; '.join(errors)}")
        else:
            print_error("Run failed.")
    elif run.status == RunStatus.cancelled:
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
