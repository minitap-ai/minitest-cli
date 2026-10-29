"""``minitest issues not-a-bug``: the webapp's "Not a bug", end to end.

An issue backed by a criterion result gets its feedback through the result, Mini
processes it (and learns a judgement rule within ``--scope``), and the issue is then
resolved — the backend refuses the status change until processing is over, so this
waits for it, as the webapp does. An issue Mini found on its own (no criterion result)
takes the feedback on the issue itself and the server resolves it at once.
"""

import asyncio
import time
from typing import Annotated, Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.feedback_scope import ScopeOpt, check_scope, scope_body, with_scope
from minitest_cli.commands.issues_fix import FIXED
from minitest_cli.commands.issues_helpers import failures_base_path, fetch_failure
from minitest_cli.commands.run_helpers import (
    ensure_uuid,
    handle_response_error,
    resolve_app,
    run_api_call,
)
from minitest_cli.core.config import Settings
from minitest_cli.models.app_failure import AppFailure
from minitest_cli.utils.output import err_console, print_json, print_warning

POLL_INTERVAL_SECONDS = 3.0
DEFAULT_TIMEOUT_SECONDS = 300


async def _post_feedback(
    client: ApiClient, path: str, text: str, scope: dict[str, Any] | None
) -> dict[str, Any]:
    resp = await client.post(path, json=with_scope({"feedbackText": text}, scope))
    handle_response_error(resp, resource="Issue")
    return resp.json()


async def _close_when_processed(
    client: ApiClient, app_id: str, issue_id: str, timeout: int
) -> AppFailure | None:
    """Resolve the issue once Mini has processed the feedback; None on timeout."""
    deadline = time.monotonic() + timeout
    with err_console.status("[bold blue]Mini is processing the feedback…"):
        while time.monotonic() < deadline:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            if (await fetch_failure(client, app_id, issue_id)).feedback_pending:
                continue
            resp = await client.patch(
                f"{failures_base_path(app_id)}/{issue_id}/status", json={"issueStatus": FIXED}
            )
            if resp.status_code == 409:
                continue
            handle_response_error(resp, resource="Issue")
            return AppFailure.model_validate(resp.json())
    return None


async def _not_a_bug(
    settings: Settings,
    app_id: str,
    issue_id: str,
    text: str,
    raw_scope: str | None,
    *,
    close: bool,
    timeout: int,
) -> dict[str, Any]:
    async with ApiClient(settings) as client:
        failure = await fetch_failure(client, app_id, issue_id)
        scope = await scope_body(client, app_id, raw_scope)
        result_id = failure.acceptance_criteria_result_id
        report: dict[str, Any] = {"issueId": issue_id, "resultId": result_id, "scope": scope}
        if result_id is None:
            path = f"{failures_base_path(app_id)}/{issue_id}/feedback"
            updated = AppFailure.model_validate(await _post_feedback(client, path, text, scope))
            if scope is not None:
                print_warning(
                    "This issue has no criterion result, so Mini learns no rule: --scope ignored."
                )
            return report | {"scope": None, "issueStatus": updated.issue_status, "closed": True}
        await _post_feedback(
            client, f"/api/v1/apps/{app_id}/issues/{result_id}/feedback", text, scope
        )
        if not close:
            return report | {"issueStatus": failure.issue_status, "closed": False}
        closed = await _close_when_processed(client, app_id, issue_id, timeout)
        if closed is None:
            return report | {"issueStatus": failure.issue_status, "closed": False, "timedOut": True}
        return report | {"issueStatus": closed.issue_status, "closed": True}


def not_a_bug(
    issue_id: Annotated[str, typer.Argument(help="Issue ID (the `id` from `issues list`).")],
    text: Annotated[
        str, typer.Argument(help="Why it is not a bug, e.g. 'The promo banner is expected here.'")
    ],
    scope: ScopeOpt = None,
    keep_open: Annotated[
        bool,
        typer.Option(
            "--keep-open",
            help="Send the feedback but leave the issue open (Mini re-judges the criterion).",
        ),
    ] = False,
    timeout: Annotated[
        int, typer.Option("--timeout", help="Seconds to wait for Mini before giving up.")
    ] = DEFAULT_TIMEOUT_SECONDS,
) -> None:
    """Mark an issue as not a bug: send the feedback, then resolve it once Mini processed it."""
    ensure_uuid(issue_id, kind="issue")
    check_scope(scope)
    settings, app_id, _ = resolve_app()
    report = run_api_call(
        _not_a_bug(settings, app_id, issue_id, text, scope, close=not keep_open, timeout=timeout)
    )
    print_json(report)
    if report.get("timedOut"):
        print_warning(
            f"Mini is still processing after {timeout}s; the feedback is saved. "
            f"Resolve it later with `minitest issues fix {issue_id}`."
        )
        raise typer.Exit(code=1)
