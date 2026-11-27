"""The end of a PR check: exit code, Markdown report, GitHub Actions summary and errors."""

import json
import os
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

import httpx
import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.api.errors import format_network_error
from minitest_cli.commands.draft_helpers import DraftTarget
from minitest_cli.commands.pr_api import EXIT_ERRORED, check_path
from minitest_cli.commands.pr_progress import in_github_actions
from minitest_cli.commands.pr_render import (
    console,
    counts_line,
    critical_annotations,
    info,
    warn,
)

EXIT_READY = 0
EXIT_NOT_READY = 1
EXIT_NEEDS_ANSWER = 2


class FailOn(StrEnum):
    CRITICAL = "critical"
    WARNING = "warning"


FailOnOpt = Annotated[
    FailOn,
    typer.Option("--fail-on", help="warning: also exit 1 on ready_with_warnings."),
]
ReportFileOpt = Annotated[
    Path | None, typer.Option("--report-file", help="Write the Markdown report to this file.")
]
TimeoutOpt = Annotated[
    float | None,
    typer.Option(
        "--timeout",
        min=1.0,
        help="Stop waiting after this many seconds (exit 3); the check keeps running.",
    ),
]


def exit_code(verdict: str | None, fail_on: FailOn) -> int:
    if verdict == "ready":
        return EXIT_READY
    if verdict == "ready_with_warnings":
        return EXIT_NOT_READY if fail_on is FailOn.WARNING else EXIT_READY
    if verdict == "not_ready":
        return EXIT_NOT_READY
    if verdict == "needs_answer":
        return EXIT_NEEDS_ANSWER
    return EXIT_ERRORED


def step_summary() -> Path | None:
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    return Path(summary) if summary and in_github_actions() else None


async def write_markdown(
    client: ApiClient, target: DraftTarget, check_id: str, push: int, report_file: Path | None
) -> None:
    """Write the server's Markdown report where asked; a failure here never hides the verdict."""
    summary = step_summary()
    if report_file is None and summary is None:
        return
    params = {**target.params, "push": push}
    try:
        resp = await client.get(check_path(check_id, "/report.md"), params=params)
    except httpx.TransportError as exc:
        warn(f"Could not read the Markdown report: {format_network_error(exc)}")
        return
    if resp.status_code >= 400:
        warn(f"Could not read the Markdown report ({resp.status_code}).")
        return
    if report_file is not None:
        report_file.write_text(resp.text, encoding="utf-8")
        info(f"Report written to {report_file}")
    if summary is not None:
        with summary.open("a", encoding="utf-8") as f:
            f.write(resp.text.rstrip("\n") + "\n")


def announce(report: dict[str, Any], code: int, url: str, *, json_mode: bool) -> None:
    if json_mode:
        result = {"verdict": report.get("verdict"), "exitCode": code, "reportUrl": url}
        line = {"type": "pr_check.result", "data": {**result, "report": report}}
        print(json.dumps(line, default=str), flush=True)  # noqa: T201
        return
    if in_github_actions():
        for annotation in critical_annotations(report):
            print(annotation, flush=True)  # noqa: T201
    pr, verdict = report.get("prNumber"), report.get("verdict") or report.get("state")
    summary = f"PR #{pr} push {report.get('push')}: {verdict} — {counts_line(report.get('counts'))}"
    style = {EXIT_READY: "green", EXIT_NEEDS_ANSWER: "yellow"}.get(code, "red")
    console.print(f"[bold {style}]{summary}[/bold {style}]")
    if code == EXIT_NEEDS_ANSWER:
        console.print(
            "Mini has a question: clarify it in the PR text and run `minitest pr check` again"
            " (the next push re-tests every check that asked), or answer it in the session."
        )
    if report.get("state") == "cancelled":
        console.print(f"A newer push replaced this one; `minitest pr wait {pr}` follows it.")
    console.print(f"Report: {url}")
