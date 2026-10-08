"""The `minitest run cancel` command: cancel the in-flight platforms of a story run.

testing-service only cancels per target (story-run platform, SRP), so the command reads
the run, then cancels each selected platform that has not finished yet.
"""

from enum import StrEnum
from typing import Annotated

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.deprecated_alias import deprecated_option, merge_deprecated_option
from minitest_cli.commands.run_display import _derive_run_status
from minitest_cli.commands.run_helpers import (
    base_path,
    ensure_uuid,
    EXIT_NOT_FOUND,
    handle_response_error,
    resolve_app,
    run_api_call,
)
from minitest_cli.models.story_run import PlatformRun, StoryRunResponse
from minitest_cli.utils.output import output, print_error, print_success

# Mirrors testing-service EXECUTION_FINISHED_STATES: the SRP cancel route answers 409 for these.
FINISHED_EXECUTION_STATES = {"evaluating", "completed", "failed", "skipped", "escalated"}


class RunPlatform(StrEnum):
    ios = "ios"
    android = "android"
    web = "web"


def _srp_cancel_path(app_id: str, srp_id: str | None) -> str:
    return f"/api/v1/apps/{app_id}/story-run-platforms/{srp_id}/cancel"


def _label(platform: PlatformRun) -> str:
    return platform.label or platform.platform


def _is_cancellable(platform: PlatformRun) -> bool:
    return (
        platform.srp_id is not None
        and platform.cancellation_requested_at is None
        and platform.execution_state not in FINISHED_EXECUTION_STATES
    )


def _select(
    run: StoryRunResponse, platform: RunPlatform | None, srp_id: str | None
) -> list[PlatformRun]:
    selected = [
        p
        for p in run.platforms
        if (platform is None or p.platform == platform.value)
        and (srp_id is None or p.srp_id == srp_id.lower())
    ]
    if not selected:
        wanted = [
            f"{platform.value} platform" if platform else "",
            f"target {srp_id}" if srp_id else "",
        ]
        print_error(f"Run {run.id} has no {' / '.join(w for w in wanted if w) or 'platforms'}.")
        raise typer.Exit(code=EXIT_NOT_FOUND)
    return selected


async def _cancel_platforms(
    client: ApiClient, app_id: str, targets: list[PlatformRun]
) -> tuple[StoryRunResponse | None, list[PlatformRun]]:
    latest: StoryRunResponse | None = None
    cancelled: list[PlatformRun] = []
    for target in targets:
        resp = await client.post(_srp_cancel_path(app_id, target.srp_id))
        if resp.status_code == 409:
            continue
        handle_response_error(resp, resource="Run platform")
        latest = StoryRunResponse.model_validate(resp.json())
        cancelled.append(target)
    return latest, cancelled


def cancel(
    run_id: Annotated[str, typer.Argument(help="Run ID to cancel.")],
    platform: Annotated[
        RunPlatform | None,
        typer.Option("--platform", help="Only cancel this platform (ios, android or web)."),
    ] = None,
    target_id: Annotated[
        str | None,
        typer.Option(
            "--target-id", help="Only cancel this target (its srpId in `run status --json`)."
        ),
    ] = None,
    legacy_srp: Annotated[str | None, deprecated_option("--srp", new_flag="--target-id")] = None,
) -> None:
    """Cancel every pending or running platform of a scenario run."""
    settings, app_id, json_mode = resolve_app()
    ensure_uuid(run_id, kind="run id")
    srp_id = merge_deprecated_option(
        target_id, legacy_srp, old_flag="--srp", new_flag="--target-id"
    )
    if srp_id is not None:
        ensure_uuid(srp_id, kind="target id")

    async def _cancel() -> tuple[StoryRunResponse, list[PlatformRun]]:
        async with ApiClient(settings) as client:
            resp = await client.get(f"{base_path(app_id)}/{run_id}")
            handle_response_error(resp, resource="Run")
            run = StoryRunResponse.model_validate(resp.json())
            targets = [p for p in _select(run, platform, srp_id) if _is_cancellable(p)]
            latest, cancelled = await _cancel_platforms(client, app_id, targets)
            return latest or run, cancelled

    run, cancelled = run_api_call(_cancel())
    if not cancelled:
        states = ", ".join(f"{_label(p)}: {p.execution_state}" for p in run.platforms)
        print_error(
            f"Nothing to cancel on run {run.id}: the selected platforms already finished "
            f"or are being cancelled ({states})."
        )
        raise typer.Exit(code=1)
    if json_mode:
        output(run.model_dump(mode="json", by_alias=True), json_mode=True)
        return
    labels = ", ".join(_label(p) for p in cancelled)
    print_success(f"Run cancelled: {run.id} ({labels}; status: {_derive_run_status(run)})")
