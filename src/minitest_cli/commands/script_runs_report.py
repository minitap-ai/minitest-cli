"""Send a Playwright JSON or JUnit report as the tests of a hub session."""

from pathlib import Path
from typing import Annotated, Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.run_helpers import (
    ensure_uuid,
    handle_response_error,
    resolve_app,
    run_api_call,
)
from minitest_cli.commands.script_runs_helpers import fetch_run, pick_test, test_label
from minitest_cli.commands.script_runs_report_parse import ReportError, parse_report
from minitest_cli.core.config import Settings
from minitest_cli.utils.output import print_error, print_json, print_success

# testing-service records at most this many attempts per call.
BATCH = 500


def report(
    run_id: Annotated[str, typer.Argument(help="Script run ID.")],
    file: Annotated[
        Path,
        typer.Option("--file", exists=True, dir_okay=False, help="Playwright JSON or JUnit XML."),
    ],
    test: Annotated[
        str | None,
        typer.Option(
            "--test", help="Hub session to attach the tests to; needed when the run has several."
        ),
    ] = None,
) -> None:
    """Record a Playwright JSON or JUnit report as a hub session's tests, for a suite that ran
    without the Minitap reporter. Re-sending the same report replaces its tests."""
    settings, app_id, json_mode = resolve_app()
    ensure_uuid(run_id, kind="script run id")
    try:
        cases = parse_report(file.read_bytes())
    except (ReportError, ValueError) as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc
    if not cases:
        print_error(f"{file} holds no test.")
        raise typer.Exit(code=1)
    session = pick_test(run_api_call(fetch_run(settings, app_id, run_id)), test)
    totals = run_api_call(_post(settings, app_id, session.scripted_run_id, cases))
    if json_mode:
        print_json({"testId": session.scripted_run_id, "sent": len(cases), **totals})
        return
    print_success(
        f"Recorded {len(cases)} test attempts on '{test_label(session)}': "
        f"{totals['tests']} tests, {totals['failures']} failed, {totals['errors']} errors."
    )


async def _post(
    settings: Settings, app_id: str, session_id: str, cases: list[dict[str, Any]]
) -> dict[str, Any]:
    path = f"/api/v1/apps/{app_id}/scripted-runs/{session_id}/cases"
    totals: dict[str, Any] = {}
    async with ApiClient(settings) as client:
        for start in range(0, len(cases), BATCH):
            resp = await client.post(path, json={"cases": cases[start : start + BATCH]})
            handle_response_error(resp, resource="Script run")
            totals = resp.json()
    return totals
