"""`minitest pr`: check a pull request on its builds, without access to its code.

CI sends the builds and the PR's text; Mini plans checks for what the PR changes and
what it could break, verifies them on devices and gives a verdict. Exit codes are the
contract CI scripts branch on: 0 ready, 1 not ready, 2 needs an answer, 3 anything
else (our side, invalid input, timeout).
"""

import json
from collections.abc import Callable, Coroutine
from typing import Annotated, Any

import typer

from minitest_cli.commands.draft_helpers import DraftTarget, run_conductor
from minitest_cli.commands.pr_api import (
    PrGroup,
    check_path,
    conductor,
    errors_exit_3,
    find_check,
    pr_target,
    raise_for_status,
    report_url,
    request,
)
from minitest_cli.commands.pr_check import register as register_check
from minitest_cli.commands.pr_outcome import FailOn, FailOnOpt, ReportFileOpt, TimeoutOpt
from minitest_cli.commands.pr_render import console
from minitest_cli.commands.pr_wait import WaitOptions, follow_push

app = typer.Typer(
    name="pr",
    cls=PrGroup,
    help="Check a pull request on its builds and follow it until merged or closed.",
    no_args_is_help=True,
)
PrArg = Annotated[int, typer.Argument(min=1, help="Pull request number.")]
register_check(app)


def _run[T](
    action: Callable[[DraftTarget], Coroutine[Any, Any, T]],
) -> tuple[DraftTarget, T]:
    target = pr_target()
    with errors_exit_3():
        return target, run_conductor(action(target))


@app.command(name="wait")
def wait(
    pr: PrArg,
    fail_on: FailOnOpt = FailOn.CRITICAL,
    report_file: ReportFileOpt = None,
    timeout: TimeoutOpt = None,
) -> None:
    """Follow the PR's latest push to its verdict; same exit codes as `pr check`."""

    async def follow(target: DraftTarget) -> int:
        async with conductor(target) as client:
            report = await find_check(client, target, pr)
            url = report_url(target, report["reportUrl"])
            if not target.json_mode:
                console.print(f"Report: {url}")
            options = WaitOptions(fail_on, report_file, timeout)
            return await follow_push(client, target, report, url, options)

    _, code = _run(follow)
    raise typer.Exit(code=code)


@app.command(name="report")
def report(
    pr: PrArg,
    push: Annotated[
        int | None, typer.Option("--push", min=1, help="Push number (default: the latest).")
    ] = None,
) -> None:
    """Print the PR check's Markdown report (the report itself with --json)."""

    async def read(target: DraftTarget) -> Any:
        async with conductor(target) as client:
            found = await find_check(client, target, pr)
            params = {} if push is None else {"push": push}
            if target.json_mode:
                path = check_path(found["id"])
                return await request(client, target, "GET", path, what="Report", params=params)
            resp = await client.get(
                check_path(found["id"], "/report.md"), params={**target.params, **params}
            )
            raise_for_status(resp, what="Report")
            return resp.text

    target, body = _run(read)
    if target.json_mode:
        print(json.dumps(body, indent=2))  # noqa: T201
    else:
        print(body, end="" if body.endswith("\n") else "\n")  # noqa: T201


def _close(pr: int, outcome: str) -> None:
    async def send(target: DraftTarget) -> Any:
        async with conductor(target) as client:
            found = await find_check(client, target, pr)
            path = check_path(found["id"], f"/{outcome}")
            return await request(client, target, "POST", path, what=f"Marking PR #{pr} {outcome}")

    target, body = _run(send)
    if target.json_mode:
        print(json.dumps(body, indent=2))  # noqa: T201
        return
    changes = body.get("suiteChanges") or []
    kinds = [c.get("kind") for c in changes]
    console.print(f"PR #{pr} {outcome}: suite changes {body.get('state')}")
    if outcome == "merged":
        applied = kinds.count("edited") + kinds.count("new")
        deleted = kinds.count("deleted")
        console.print(f"{applied} change(s) applied; {deleted} deletion(s) wait for approval.")
    elif changes:
        console.print(f"{len(changes)} proposed change(s) discarded; the suite is unchanged.")


@app.command(name="merged")
def merged(pr: PrArg) -> None:
    """The PR merged: apply Mini's suite edits and new scenarios (deletions wait for a person)."""
    _close(pr, "merged")


@app.command(name="closed")
def closed(pr: PrArg) -> None:
    """The PR closed without merging: discard Mini's suite changes."""
    _close(pr, "closed")
