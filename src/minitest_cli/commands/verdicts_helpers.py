"""Projection logic for the `run verdicts` command.

Turns a batch plus its per-story criterion leaves into a compact, product-level
pass/fail structure. Criterion leaves live only on the story-run detail endpoint,
so we fan out one detail request per story run.
"""

import asyncio

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.batch_helpers import batches_base_path
from minitest_cli.commands.run_helpers import base_path, handle_response_error
from minitest_cli.core.config import Settings
from minitest_cli.models.batch import BatchResponse, BatchTargetView
from minitest_cli.models.story_run import (
    BatchVerdictsResponse,
    CriterionResult,
    PlatformRun,
    StoryRunResponse,
    VerdictCriterion,
    VerdictStory,
    VerdictStoryPlatform,
    VerdictTarget,
)

SUCCESS_STATUS = "success"
VALID_PLATFORMS = ("ios", "android", "web")


def _project_target(target: BatchTargetView) -> VerdictTarget:
    counters = target.counters
    return VerdictTarget(
        platform=target.platform,
        build_id=target.build_id,
        verdict=counters.verdict,
        execution_state=counters.execution_state,
        passed=counters.passed,
        criticals=counters.criticals,
        warnings=counters.warnings,
        skipped=counters.skipped,
        failed_infra=counters.failed_infra,
        skipped_by_cascade=counters.skipped_by_cascade,
    )


def _project_platform(platform_run: PlatformRun) -> VerdictStoryPlatform:
    return VerdictStoryPlatform(
        platform=platform_run.platform,
        verdict=platform_run.verdict,
        execution_state=platform_run.execution_state,
        skip_reason=platform_run.skip_reason,
        build_id=str(platform_run.build_id) if platform_run.build_id else None,
        recording_path=platform_run.recording_path,
        session_paths=platform_run.session_paths,
        criticals=platform_run.criticals,
        warnings=platform_run.warnings,
        skipped=platform_run.skipped,
    )


def _project_criterion(result: CriterionResult, *, verbose: bool) -> VerdictCriterion:
    return VerdictCriterion(
        platform=result.platform,
        status=result.status,
        criticality=result.criticality,
        fail_reason=result.fail_reason,
        result_summary=result.result_summary,
        confidence=result.confidence,
        content=result.content,
        evidence=result.evidence if verbose else None,
    )


def project_story(
    run: StoryRunResponse,
    *,
    platform: str | None,
    only_failed: bool,
    verbose: bool,
) -> VerdictStory | None:
    platforms = [p for p in run.platforms if platform is None or p.platform == platform]
    results = [r for r in run.results if platform is None or r.platform == platform]

    if platform is not None and not platforms and not results:
        return None

    has_failure = any(r.status != SUCCESS_STATUS for r in results)
    if only_failed and not has_failure:
        return None

    criteria_src = results if verbose else [r for r in results if r.status != SUCCESS_STATUS]
    return VerdictStory(
        user_story_name=run.user_story_name,
        story_run_id=run.id,
        platforms=[_project_platform(p) for p in platforms],
        criteria=[_project_criterion(r, verbose=verbose) for r in criteria_src],
    )


async def _fetch_story(client: ApiClient, app_id: str, story_run_id: str) -> StoryRunResponse:
    resp = await client.get(f"{base_path(app_id)}/{story_run_id}")
    handle_response_error(resp, resource="Run")
    return StoryRunResponse.model_validate(resp.json())


async def fetch_verdicts(
    settings: Settings,
    app_id: str,
    batch_id: str,
    *,
    platform: str | None,
    only_failed: bool,
    verbose: bool,
) -> BatchVerdictsResponse:
    async with ApiClient(settings) as client:
        resp = await client.get(f"{batches_base_path(app_id)}/{batch_id}")
        handle_response_error(resp, resource="Batch")
        batch = BatchResponse.model_validate(resp.json())
        runs = await asyncio.gather(
            *(_fetch_story(client, app_id, sr.id) for sr in batch.story_runs)
        )

    targets = [
        _project_target(t) for t in batch.targets if platform is None or t.platform == platform
    ]
    stories = [
        story
        for run in runs
        if (
            story := project_story(run, platform=platform, only_failed=only_failed, verbose=verbose)
        )
        is not None
    ]
    return BatchVerdictsResponse(
        batch_id=batch.id, app_id=batch.app_id, targets=targets, stories=stories
    )
