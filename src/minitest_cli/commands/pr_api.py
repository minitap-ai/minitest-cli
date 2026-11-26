"""Conductor calls for `minitest pr`, where every failure on our side exits 3.

CI scripts branch on the exit code (1 not ready, 2 needs an answer), so an auth,
network, usage or server error must never surface as 1 or 2.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from urllib.parse import urljoin

import click
import httpx
import typer
from typer.core import TyperGroup

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.draft_helpers import DraftTarget, resolve_target
from minitest_cli.commands.run_helpers import extract_detail
from minitest_cli.commands.pr_render import error

EXIT_ERRORED = 3
PR_CHECKS_PATH = "/api/v1/pr-checks"


class PrGroup(TyperGroup):
    def invoke(self, ctx: click.Context) -> Any:
        try:
            return super().invoke(ctx)
        except click.UsageError as exc:
            exc.exit_code = EXIT_ERRORED
            raise


@contextmanager
def errors_exit_3() -> Iterator[None]:
    try:
        yield
    except click.exceptions.Exit as exc:
        if exc.exit_code:
            raise typer.Exit(code=EXIT_ERRORED) from exc
        raise
    except SystemExit as exc:
        if exc.code:
            raise typer.Exit(code=EXIT_ERRORED) from exc
        raise


def pr_target() -> DraftTarget:
    with errors_exit_3():
        return resolve_target()


def check_path(check_id: str, suffix: str = "") -> str:
    return f"{PR_CHECKS_PATH}/{check_id}{suffix}"


def app_pr_path(target: DraftTarget, pr_number: int) -> str:
    return f"/api/v1/apps/{target.app_id}/pr-checks/{pr_number}"


def report_url(target: DraftTarget, url: str) -> str:
    return urljoin(target.settings.webapp_url, url)


def conductor(target: DraftTarget) -> ApiClient:
    return ApiClient(target.settings, base_url=target.settings.conductor_url)


def raise_for_status(resp: httpx.Response, *, what: str) -> None:
    if resp.status_code < 400:
        return
    detail = extract_detail(resp)
    if resp.status_code in (401, 403):
        error(f"Not allowed ({resp.status_code}): {detail or 'credentials rejected.'}")
    elif resp.status_code == 404:
        error(detail or f"{what} not found.")
    else:
        error(f"{what} failed ({resp.status_code}): {detail or resp.text}")
    raise typer.Exit(code=EXIT_ERRORED)


async def request(
    client: ApiClient, target: DraftTarget, method: str, path: str, *, what: str, **kwargs: Any
) -> Any:
    params = {**target.params, **kwargs.pop("params", {})}
    resp = await client.request(method, path, params=params, **kwargs)
    raise_for_status(resp, what=what)
    return resp.json()


async def find_check(client: ApiClient, target: DraftTarget, pr_number: int) -> dict[str, Any]:
    """The report of the app's PR check for this PR number (latest push)."""
    path = app_pr_path(target, pr_number)
    return await request(client, target, "GET", path, what=f"PR check for PR #{pr_number}")
