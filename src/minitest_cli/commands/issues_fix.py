"""Mark app failures as fixed."""

from typing import Annotated, NotRequired, TypedDict

import httpx
import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.api.errors import format_network_error
from minitest_cli.commands.run_helpers import extract_detail, is_uuid, resolve_app, run_api_call
from minitest_cli.core.config import Settings
from minitest_cli.utils.output import print_json


class FixResult(TypedDict):
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


async def _fix_issues(
    settings: Settings, app_id: str, issue_ids: list[str]
) -> tuple[list[FixResult], list[int]]:
    results: list[FixResult] = []
    exit_codes: list[int] = []
    async with ApiClient(settings) as client:
        for issue_id in issue_ids:
            if not is_uuid(issue_id):
                results.append(
                    {"issueId": issue_id, "status": "failed", "error": "Invalid issue ID."}
                )
                exit_codes.append(1)
                continue
            try:
                response = await client.patch(
                    f"/api/v1/apps/{app_id}/failures/{issue_id}/status",
                    json={"issueStatus": "fixed"},
                )
            except httpx.HTTPError as exc:
                results.append(
                    {"issueId": issue_id, "status": "failed", "error": format_network_error(exc)}
                )
                exit_codes.append(3)
                continue
            if response.status_code >= 400:
                results.append(
                    {"issueId": issue_id, "status": "failed", "error": _response_error(response)}
                )
                exit_codes.append(_response_exit_code(response))
                continue
            results.append({"issueId": issue_id, "status": "fixed"})
    return results, exit_codes


def fix(
    issue_ids: Annotated[
        list[str],
        typer.Argument(help="One or more app-failure IDs to mark as fixed."),
    ],
) -> None:
    """Mark findings as fixed, reporting one result per ID."""
    settings, app_id, _ = resolve_app()
    results, exit_codes = run_api_call(_fix_issues(settings, app_id, issue_ids))
    fixed = sum(result["status"] == "fixed" for result in results)
    payload = {"results": results, "fixed": fixed, "failed": len(results) - fixed}
    print_json(payload)
    if exit_codes:
        if fixed:
            raise typer.Exit(code=1)
        if all(code == 4 for code in exit_codes):
            raise typer.Exit(code=4)
        if all(code == 2 for code in exit_codes):
            raise typer.Exit(code=2)
        if any(code == 3 for code in exit_codes):
            raise typer.Exit(code=3)
        raise typer.Exit(code=1)
