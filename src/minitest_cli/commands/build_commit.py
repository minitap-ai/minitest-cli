"""``minitest build from-commit``: queue a build from a GitHub commit."""

from typing import Annotated, Any

import typer

from minitest_cli.commands.build_commit_resolve import (
    RUN_START_FLAGS,
    resolve_testing_service_ids,
)
from minitest_cli.commands.build_helpers import resolve_app, run_api_call
from minitest_cli.commands.commit_helpers import (
    CommitShaArg,
    PlatformOpt,
    trigger_commit_build,
    validate_commit_sha,
    validate_platforms,
)
from minitest_cli.commands.env_helpers import resolve_app_and_tenant
from minitest_cli.models.commit_build import TriggerBuildResponse, TriggeredBuild
from minitest_cli.utils.output import (
    err_console,
    output,
    print_info,
    print_success,
    print_warning,
)

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


def trigger_payload(
    result: TriggerBuildResponse, testing_service_ids: dict[str, str | None]
) -> dict[str, Any]:
    """Emit both id spaces.

    ``buildId`` keeps its historical meaning (the apps-manager id) so existing
    CI consumers do not break; ``appsManagerBuildId`` is the unambiguous alias
    for the same value, and ``testingServiceBuildId`` is the one to hand to
    ``minitest run start`` — ``null`` when it could not be resolved.
    """
    return {
        "builds": [
            {
                "buildId": build.id,
                "appsManagerBuildId": build.id,
                "testingServiceBuildId": testing_service_ids.get(build.id),
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


def print_build_ids(build: TriggeredBuild, testing_service_id: str | None) -> None:
    """Label both ids, so the one ``run start`` accepts is never in doubt."""
    print_success(f"Build queued: {build.platform}, {build.status}")
    err_console.print(f"  apps-manager build id:    [dim]{build.id}[/dim]")
    flag = RUN_START_FLAGS.get(build.platform or "")
    if testing_service_id is None:
        err_console.print("  testing-service build id: [yellow]unresolved[/yellow]")
        target = f"`minitest run start {flag}`" if flag else "`minitest run start`"
        print_warning(
            f"Could not resolve the testing-service build id for {build.platform}. "
            f"{target} rejects the apps-manager id above. "
            f"Run `minitest build list --platform {build.platform}` and use the id of "
            f"the row for commit {(build.commit_sha or '')[:7] or 'this build'}."
        )
        return
    usage = (
        f"pass this to `minitest run start {flag}`" if flag else "this is the id `build list` shows"
    )
    err_console.print(f"  testing-service build id: [bold]{testing_service_id}[/bold]  ← {usage}")


def from_commit(
    commit_sha: CommitShaArg = None,
    platform: PlatformOpt = None,
    force_full: ForceFullOpt = False,
) -> None:
    """Queue a build from a GitHub commit, without running any test."""
    settings, app_id, json_mode = resolve_app()
    sha = validate_commit_sha(commit_sha)
    platforms = validate_platforms(platform)

    async def _run() -> tuple[TriggerBuildResponse, dict[str, str | None]]:
        _, tenant_id = await resolve_app_and_tenant(settings, app_id)
        triggered = await trigger_commit_build(
            settings,
            tenant_id=tenant_id,
            app_id=app_id,
            commit_sha=sha,
            platforms=platforms,
            force_full_build=force_full,
        )
        return triggered, await resolve_testing_service_ids(settings, app_id, triggered.builds)

    result, testing_service_ids = run_api_call(_run())
    payload = trigger_payload(result, testing_service_ids)

    if json_mode:
        output(payload, json_mode=True)
        return

    for build in result.builds:
        print_build_ids(build, testing_service_ids.get(build.id))
    if result.deduplicated:
        print_info(
            f"Reused an existing build for: {', '.join(result.deduplicated)}. "
            "Pass --force-full to skip the incremental build cache check."
        )
    if not result.builds:
        print_info("No build was queued for the requested platforms.")
    output(payload, json_mode=False)
