"""``minitest build from-commit``: queue a build from a GitHub commit."""

from typing import Annotated, Any

import typer

from minitest_cli.commands.build_helpers import resolve_app, run_api_call
from minitest_cli.commands.commit_helpers import (
    CommitShaArg,
    PlatformOpt,
    trigger_commit_build,
    validate_commit_sha,
    validate_platforms,
)
from minitest_cli.commands.env_helpers import resolve_app_and_tenant
from minitest_cli.models.commit_build import TriggerBuildResponse
from minitest_cli.utils.output import output, print_info, print_success

ForceFullOpt = Annotated[
    bool,
    typer.Option(
        "--force-full",
        help=(
            "Skip the incremental build cache check. A matching build that is already "
            "pending or building can still be reused."
        ),
    ),
]


def trigger_payload(result: TriggerBuildResponse) -> dict[str, Any]:
    return {
        "builds": [
            {
                "buildId": build.id,
                "platform": build.platform,
                "status": build.status,
                "commitSha": build.commit_sha,
                "commitTitle": build.commit_title,
                "branch": build.branch,
                "previewUrl": build.preview_url,
            }
            for build in result.builds
        ],
        "deduplicated": result.deduplicated,
    }


def from_commit(
    commit_sha: CommitShaArg = None,
    platform: PlatformOpt = None,
    force_full: ForceFullOpt = False,
) -> None:
    """Queue a build from a GitHub commit, without running any test."""
    settings, app_id, json_mode = resolve_app()
    sha = validate_commit_sha(commit_sha)
    platforms = validate_platforms(platform)

    async def _run() -> TriggerBuildResponse:
        _, tenant_id = await resolve_app_and_tenant(settings, app_id)
        return await trigger_commit_build(
            settings,
            tenant_id=tenant_id,
            app_id=app_id,
            commit_sha=sha,
            platforms=platforms,
            force_full_build=force_full,
        )

    result = run_api_call(_run())
    payload = trigger_payload(result)

    if json_mode:
        output(payload, json_mode=True)
        return

    for build in result.builds:
        print_success(f"Build queued: {build.id} ({build.platform}, {build.status})")
    if result.deduplicated:
        print_info(
            f"Reused an existing build for: {', '.join(result.deduplicated)}. "
            "Pass --force-full to skip the incremental build cache check."
        )
    if not result.builds:
        print_info("No build was queued for the requested platforms.")
    output(payload, json_mode=False)
