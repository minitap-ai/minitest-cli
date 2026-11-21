"""Script runs: list and inspect the app's own test suites that ran on Minitap."""

from enum import StrEnum
from typing import Annotated

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.run_helpers import (
    ensure_uuid,
    handle_response_error,
    resolve_app,
    run_api_call,
)
from minitest_cli.commands.script_runs_artifacts import register_artifact_commands
from minitest_cli.commands.script_runs_helpers import (
    device_label,
    failure_reason,
    fetch_run,
    minitap_issue,
    script_runs_path,
    test_label,
)
from minitest_cli.models.script_run import ScriptRunDetail, ScriptRunList, ScriptRunSummary
from minitest_cli.utils.output import output, print_info, print_table

app = typer.Typer(
    name="script-runs",
    help="List and inspect your own test suites run on Minitap (Script runs in the webapp).",
)


class RunStatus(StrEnum):
    running = "running"
    passed = "passed"
    failed = "failed"
    unmarked = "unmarked"


def _run_label(run: ScriptRunSummary) -> str:
    if run.run_name or run.session_name:
        return run.run_name or run.session_name or ""
    return f"commit {run.commit_sha[:10]}" if run.commit_sha else run.run_id


def _shorten(text: str | None, width: int = 80) -> str:
    line = " ".join((text or "").split())
    return line if len(line) <= width else f"{line[: width - 1]}…"


@app.command(name="list")
def list_runs(
    status: Annotated[RunStatus | None, typer.Option(help="Only runs in this status.")] = None,
    framework: Annotated[
        str | None, typer.Option(help="Only runs with a test of this framework (e.g. appium).")
    ] = None,
    search: Annotated[
        str | None, typer.Option(help="Run or test name contains it, or commit starts with it.")
    ] = None,
    limit: Annotated[int, typer.Option(min=1, max=100, help="Runs per page.")] = 25,
    offset: Annotated[int, typer.Option(min=0, help="Runs to skip.")] = 0,
) -> None:
    """List the app's script runs, most recently started first."""
    settings, app_id, json_mode = resolve_app()
    filters = {"status": status, "framework": framework, "search": search}
    params: dict[str, object] = {"limit": limit, "offset": offset}
    params.update({key: str(value) for key, value in filters.items() if value})

    async def _list() -> ScriptRunList:
        async with ApiClient(settings) as client:
            resp = await client.get(script_runs_path(app_id), params=params)
        handle_response_error(resp, resource="Script runs")
        return ScriptRunList.model_validate(resp.json())

    result = run_api_call(_list())
    if json_mode:
        output(result.model_dump(mode="json", by_alias=True), json_mode=True)
        return
    if not result.script_runs:
        print_info("No script runs found.")
        return
    rows = [
        [
            run.run_id,
            _shorten(_run_label(run), 40),
            run.status,
            f"{run.totals.tests - run.totals.failures - run.totals.errors}/{run.totals.tests}",
            str(run.session_count),
            str(run.infra_issue_count or ""),
            run.started_at.strftime("%Y-%m-%d %H:%M"),
        ]
        for run in result.script_runs
    ]
    shown = f"{offset + 1}–{offset + len(rows)} of {result.total}"
    print_table(
        ["Run ID", "Run", "Status", "Passed", "Tests", "Minitap issues", "Started"],
        rows,
        title=f"Script runs — {shown}",
    )
    if offset + len(rows) < result.total:
        print_info(f"Use --offset {offset + len(rows)} to see more.")


@app.command(name="get")
def get_run(
    run_id: Annotated[str, typer.Argument(help="Script run ID.")],
) -> None:
    """Get one script run: each test with its status, failure reason and Minitap-side issue."""
    settings, app_id, json_mode = resolve_app()
    ensure_uuid(run_id, kind="script run id")
    run: ScriptRunDetail = run_api_call(fetch_run(settings, app_id, run_id))
    if json_mode:
        output(run.model_dump(mode="json", by_alias=True), json_mode=True)
        return
    print_info(f"Script run {run.run_id} — {run.status} ({_run_label(run)})")
    if run.commit_sha:
        print_info(f"  commit: {run.commit_sha}")
    rows = [
        [
            session.scripted_run_id,
            _shorten(test_label(session), 40),
            session.status,
            device_label(session),
            _shorten(failure_reason(session)),
            _shorten(minitap_issue(session)),
        ]
        for session in run.sessions
    ]
    print_table(
        ["Test ID", "Test", "Status", "Device", "Failure", "Minitap issue"],
        rows,
        title=f"Tests ({len(rows)})",
    )


register_artifact_commands(app)
