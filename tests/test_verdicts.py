"""Projection logic for `minitest run verdicts`.

These exercise the real projection functions over hand-built model
fixtures (no HTTP, no mocks) so a regression in what the command
surfaces — passing criteria, evidence, cascade skips — actually fails.
"""

from datetime import datetime

from minitest_cli.commands.verdicts_helpers import (
    _project_target,
    project_story,
)
from minitest_cli.models.batch import BatchCounters, BatchTargetView
from minitest_cli.models.story_run import (
    CriterionResult,
    PlatformRun,
    StoryRunResponse,
)

_NOW = datetime(2024, 1, 1, 12, 0, 0)


def _criterion(
    *,
    platform: str,
    status: str,
    evidence: str | None = None,
    content: str | None = None,
) -> CriterionResult:
    return CriterionResult(
        id=f"crit-{platform}-{status}",
        story_run_id="run-1",
        criterion_version_id="cv-1",
        platform=platform,
        status=status,
        success=status == "success",
        evidence=evidence,
        content=content,
        created_at=_NOW,
    )


def _story(*, platforms: list[str], results: list[CriterionResult]) -> StoryRunResponse:
    return StoryRunResponse(
        id="run-1",
        user_story_id="us-1",
        user_story_name="Checkout works",
        platforms=[PlatformRun(platform=p) for p in platforms],
        created_at=_NOW,
        results=results,
    )


class TestVerdictProjection:
    def test_project_story_default_hides_passing_and_evidence(self) -> None:
        story = _story(
            platforms=["ios"],
            results=[
                _criterion(platform="ios", status="success"),
                _criterion(platform="ios", status="failed", evidence="screenshot"),
            ],
        )

        projected = project_story(story, platform=None, only_failed=False, verbose=False)

        assert projected is not None
        assert [c.status for c in projected.criteria] == ["failed"]
        assert projected.criteria[0].evidence is None

    def test_project_story_verbose_includes_passing_and_evidence(self) -> None:
        story = _story(
            platforms=["ios"],
            results=[
                _criterion(platform="ios", status="success"),
                _criterion(platform="ios", status="failed", evidence="screenshot"),
            ],
        )

        projected = project_story(story, platform=None, only_failed=False, verbose=True)

        assert projected is not None
        assert {c.status for c in projected.criteria} == {"success", "failed"}
        failed = next(c for c in projected.criteria if c.status == "failed")
        assert failed.evidence == "screenshot"

    def test_project_story_only_failed_drops_all_passing_story(self) -> None:
        passing = _story(
            platforms=["ios"],
            results=[_criterion(platform="ios", status="success")],
        )
        failing = _story(
            platforms=["ios"],
            results=[_criterion(platform="ios", status="failed")],
        )

        assert project_story(passing, platform=None, only_failed=True, verbose=False) is None
        assert project_story(failing, platform=None, only_failed=True, verbose=False) is not None

    def test_project_story_platform_filter_scopes_and_drops_unmatched(self) -> None:
        mixed = _story(
            platforms=["ios", "android"],
            results=[
                _criterion(platform="ios", status="failed"),
                _criterion(platform="android", status="failed"),
            ],
        )
        android_only = _story(
            platforms=["android"],
            results=[_criterion(platform="android", status="failed")],
        )

        projected = project_story(mixed, platform="ios", only_failed=False, verbose=False)

        assert projected is not None
        assert [p.platform for p in projected.platforms] == ["ios"]
        assert [c.platform for c in projected.criteria] == ["ios"]
        assert project_story(android_only, platform="ios", only_failed=False, verbose=False) is None

    def test_project_target_surfaces_verdict_and_cascade(self) -> None:
        target = BatchTargetView(
            id="bt-1",
            platform="web",
            build_id="build-9",
            label="web · chromium",
            counters=BatchCounters(
                verdict="warning",
                execution_state="completed",
                passed=3,
                warnings=1,
                skipped_by_cascade=2,
            ),
        )

        projected = _project_target(target)

        assert projected.platform == "web"
        assert projected.build_id == "build-9"
        assert projected.verdict == "warning"
        assert projected.passed == 3
        assert projected.skipped_by_cascade == 2
