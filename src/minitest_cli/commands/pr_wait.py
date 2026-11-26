"""Follow one push of a PR check to its verdict and turn it into the exit code."""

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.draft_helpers import DraftTarget
from minitest_cli.commands.pr_api import EXIT_ERRORED
from minitest_cli.commands.pr_follow import REPORT_EVENT, Event, Follower
from minitest_cli.commands.pr_outcome import (
    FailOn,
    announce,
    exit_code,
    write_markdown,
)
from minitest_cli.commands.pr_progress import Progress
from minitest_cli.commands.pr_render import console

REPORT_ATTEMPTS = 5


@dataclass(frozen=True)
class WaitOptions:
    fail_on: FailOn
    report_file: Path | None
    timeout: float | None


async def _follow(progress: Progress, follower: Follower, timeout: float | None) -> bool:
    """Feed events to ``progress`` until it finishes; False when the timeout came first."""
    deadline = None if timeout is None else time.monotonic() + timeout
    queue: asyncio.Queue[Event] = asyncio.Queue()
    producer = asyncio.create_task(follower.run(queue))
    getter = asyncio.ensure_future(queue.get())
    try:
        while not progress.finished:
            wait = progress.heartbeat_in()
            if deadline is not None:
                wait = min(wait, max(0.0, deadline - time.monotonic()))
            done, _ = await asyncio.wait(
                {getter, producer}, timeout=wait, return_when=asyncio.FIRST_COMPLETED
            )
            if getter in done:
                progress.feed(getter.result())
                getter = asyncio.ensure_future(queue.get())
            elif producer in done:
                producer.result()
            elif deadline is not None and time.monotonic() >= deadline:
                return False
            else:
                progress.heartbeat()
        return True
    finally:
        getter.cancel()
        producer.cancel()
        progress.close()


async def _final_report(follower: Follower) -> dict[str, Any] | None:
    for attempt in range(REPORT_ATTEMPTS):
        report = await follower.report()
        if report is not None:
            return report
        await asyncio.sleep(attempt + 1)
    return None


async def follow_push(
    client: ApiClient,
    target: DraftTarget,
    snapshot: dict[str, Any],
    url: str,
    options: WaitOptions,
) -> int:
    """Follow the push ``snapshot`` (a report or the create response) describes."""
    check_id, push, pr = snapshot["id"], snapshot["push"], snapshot["prNumber"]
    progress = Progress(push, json_mode=target.json_mode)
    follower = Follower(client, target, check_id, push)
    if "checks" in snapshot:
        progress.feed(Event(REPORT_EVENT, snapshot))
    if not progress.finished and not await _follow(progress, follower, options.timeout):
        console.print(
            f"[yellow]Stopped waiting after {options.timeout:.0f}s; the check keeps running."
            f" Follow it with `minitest pr wait {pr}`.[/yellow]"
        )
        return EXIT_ERRORED
    if progress.superseded_by is not None:
        console.print(
            f"[yellow]Push {push} was replaced by push {progress.superseded_by};"
            f" follow it with `minitest pr wait {pr}`.[/yellow]"
        )
        return EXIT_ERRORED
    report = await _final_report(follower)
    if report is None:
        console.print(f"[red]The verdict is in but the report cannot be read.[/red] Report: {url}")
        return EXIT_ERRORED
    code = exit_code(report.get("verdict"), options.fail_on)
    await write_markdown(client, target, check_id, push, options.report_file)
    announce(report, code, url, json_mode=target.json_mode)
    return code
