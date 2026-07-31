"""Pure projection rules for the `run verdicts` command.

Decides *what* a verdict read exposes: which criterion leaves are worth
surfacing, and which fields are replay detail rather than triage signal.
Kept free of I/O so the rules stay directly testable.
"""

from minitest_cli.models.batch import BatchTargetView
from minitest_cli.models.story_run import (
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
ACTIONABLE_STATUSES = ("failed", "unprocessable")
ACTIONABLE_CRITICALITIES = ("critical", "warning")


def is_actionable(result: CriterionResult) -> bool:
    """Whether a criterion result warrants triage.

    ``status != success`` alone is far too broad: cascade skips and
    passing-but-unprocessable leaves share that shape, so a plain
    ``--only-failed`` read ships roughly half its rows purely for the
    reader to discard. Actionable means the criterion genuinely did not
    hold *and* the failure carries product-level weight.
    """
    return result.status in ACTIONABLE_STATUSES and result.criticality in ACTIONABLE_CRITICALITIES


def project_target(target: BatchTargetView) -> VerdictTarget:
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


def _project_platform(platform_run: PlatformRun, *, verbose: bool) -> VerdictStoryPlatform:
    build_id = str(platform_run.build_id) if platform_run.build_id else None
    return VerdictStoryPlatform(
        platform=platform_run.platform,
        verdict=platform_run.verdict,
        execution_state=platform_run.execution_state,
        skip_reason=platform_run.skip_reason,
        build_id=build_id if verbose else None,
        recording_path=platform_run.recording_path if verbose else None,
        session_paths=platform_run.session_paths if verbose else None,
        criticals=platform_run.criticals,
        warnings=platform_run.warnings,
        skipped=platform_run.skipped,
    )


def _project_criterion(result: CriterionResult, *, verbose: bool) -> VerdictCriterion:
    return VerdictCriterion(
        result_id=result.id,
        criterion_id=result.criterion_id,
        criterion_version_id=result.criterion_version_id,
        platform=result.platform,
        status=result.status,
        criticality=result.criticality,
        fail_reason=result.fail_reason,
        result_summary=result.result_summary,
        confidence=result.confidence if verbose else None,
        content=result.content,
        evidence=result.evidence if verbose else None,
    )


def _select_criteria(
    results: list[CriterionResult], *, actionable: bool, verbose: bool
) -> list[CriterionResult]:
    if actionable:
        return [r for r in results if is_actionable(r)]
    if verbose:
        return results
    return [r for r in results if r.status != SUCCESS_STATUS]


def project_story(
    run: StoryRunResponse,
    *,
    platform: str | None,
    only_failed: bool,
    verbose: bool,
    actionable: bool = False,
    user_story_name: str | None = None,
) -> VerdictStory | None:
    platforms = [p for p in run.platforms if platform is None or p.platform == platform]
    results = [r for r in run.results if platform is None or r.platform == platform]

    if platform is not None and not platforms and not results:
        return None

    criteria = _select_criteria(results, actionable=actionable, verbose=verbose)
    if actionable and not criteria:
        return None
    if only_failed and not any(r.status != SUCCESS_STATUS for r in results):
        return None

    return VerdictStory(
        user_story_id=run.user_story_id,
        # The story-run detail endpoint never populates the name; the batch
        # payload already carries it, so the caller passes it back down
        # rather than making the reader join it from a separate listing.
        user_story_name=user_story_name or run.user_story_name,
        story_run_id=run.id,
        platforms=[_project_platform(p, verbose=verbose) for p in platforms],
        criteria=[_project_criterion(r, verbose=verbose) for r in criteria],
    )
