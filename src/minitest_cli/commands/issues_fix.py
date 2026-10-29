"""Move issues between triage states: fixed (Resolved), archived, back to open."""

from typing import Annotated, NotRequired, TypedDict

import httpx
import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.api.errors import format_network_error
from minitest_cli.commands.run_helpers import extract_detail, is_uuid, resolve_app, run_api_call
from minitest_cli.core.config import Settings
from minitest_cli.utils.output import print_json

# Client-side name -> server issue status. The webapp's Archive is `acknowledged`;
# Reopen (from Resolved or Archived) is `review`, the open state.
FIXED = "fixed"
ARCHIVED = "acknowledged"
OPEN = "review"
_LABELS = {FIXED: "fixed", ARCHIVED: "archived", OPEN: "open"}

IssueIdsArg = Annotated[list[str], typer.Argument(help="One or more issue IDs.")]


class StatusResult(TypedDict):
    issueId: str
    status: str
    error: NotRequired[str]


def _response_error(response: httpx.Response) -> str:
    if response.status_code == 409:
        return "Finding feedback is still processing. Retry after processing completes."
    if response.status_code == 404:
        return extract_detail(response) or "Finding not found."
    return extract_detail(response) or f"API error: {response.status_code}"


def _response_exit_code(response: httpx.Response) -> int:
    if response.status_code in {401, 403}:
        return 2
    if response.status_code == 404:
        return 4
    return 3


class _StatusError(Exception):
    def __init__(self, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.exit_code = exit_code


async def _set_one(client: ApiClient, app_id: str, issue_id: str, issue_status: str) -> None:
    """PATCH one issue's status; raises _StatusError with the exit code it deserves."""
    response = await client.patch(
        f"/api/v1/apps/{app_id}/failures/{issue_id}/status",
        json={"issueStatus": issue_status},
    )
    if response.status_code >= 400:
        raise _StatusError(_response_error(response), _response_exit_code(response))


async def set_issue_status(
    settings: Settings, app_id: str, issue_ids: list[str], issue_status: str
) -> tuple[list[StatusResult], list[int]]:
    results: list[StatusResult] = []
    exit_codes: list[int] = []
    label = _LABELS[issue_status]
    async with ApiClient(settings) as client:
        for issue_id in issue_ids:
            error: str | None = None
            code = 1
            if not is_uuid(issue_id):
                error = "Invalid issue ID."
            else:
                try:
                    await _set_one(client, app_id, issue_id, issue_status)
                except httpx.HTTPError as exc:
                    error, code = format_network_error(exc), 3
                except _StatusError as exc:
                    error, code = str(exc), exc.exit_code
            if error is None:
                results.append({"issueId": issue_id, "status": label})
                continue
            results.append({"issueId": issue_id, "status": "failed", "error": error})
            exit_codes.append(code)
    return results, exit_codes


def _report(issue_ids: list[str], issue_status: str) -> None:
    settings, app_id, _ = resolve_app()
    results, exit_codes = run_api_call(set_issue_status(settings, app_id, issue_ids, issue_status))
    done = sum(result["status"] != "failed" for result in results)
    payload = {"results": results, _LABELS[issue_status]: done, "failed": len(results) - done}
    print_json(payload)
    if exit_codes:
        if done:
            raise typer.Exit(code=1)
        for code in (4, 2):
            if all(c == code for c in exit_codes):
                raise typer.Exit(code=code)
        raise typer.Exit(code=3 if 3 in exit_codes else 1)


def fix(issue_ids: IssueIdsArg) -> None:
    """Mark issues as fixed (Resolved in the webapp), reporting one result per ID."""
    _report(issue_ids, FIXED)


def archive(issue_ids: IssueIdsArg) -> None:
    """Archive issues (kept out of the open list without calling them fixed)."""
    _report(issue_ids, ARCHIVED)


def reopen(issue_ids: IssueIdsArg) -> None:
    """Move resolved or archived issues back to open."""
    _report(issue_ids, OPEN)
