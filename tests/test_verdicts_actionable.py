"""What a verdict read exposes to a triage reader.

`--only-failed` filters on status alone, so cascade skips and passing
leaves ride along; `--actionable` narrows to criteria that genuinely did
not hold and carry product-level weight. These also pin the identity and
verbose-gating guarantees the run-overview loop depends on.
"""

from datetime import datetime
from uuid import UUID

from minitest_cli.commands.verdicts_projection import is_actionable, project_story
from minitest_cli.models.story_run import CriterionResult, PlatformRun, StoryRunResponse

_NOW = datetime(2024, 1, 1, 12, 0, 0)
_BUILD_ID = UUID("00000000-0000-0000-0000-0000000000b7")


def _criterion(*, status: str, criticality: str | None = None) -> CriterionResult:
    return CriterionResult(
        id=f"crit-{status}-{criticality}",
        story_run_id="run-1",
        criterion_version_id="cv-1",
        platform="ios",
        status=status,
        criticality=criticality,
        success=status == "success",
        confidence=90,
        created_at=_NOW,
    )


def _story(results: list[CriterionResult], *, name: str | None = None) -> StoryRunResponse:
    return StoryRunResponse(
        id="run-1",
        user_story_id="us-1",
        user_story_name=name,
        platforms=[
            PlatformRun(
                platform="ios",
                build_id=_BUILD_ID,
                recording_path="rec/ios.mp4",
                session_paths=["sess/ios.json"],
            )
        ],
        created_at=_NOW,
        results=results,
    )


class TestActionableFilter:
    def test_is_actionable_requires_failure_and_weight(self) -> None:
        assert is_actionable(_criterion(status="failed", criticality="critical"))
        assert is_actionable(_criterion(status="failed", criticality="warning"))
        assert is_actionable(_criterion(status="unprocessable", criticality="warning"))
        # Non-success but carries no product weight — noise for triage.
        assert not is_actionable(_criterion(status="skipped", criticality="pass"))
        assert not is_actionable(_criterion(status="unprocessable", criticality="pass"))
        assert not is_actionable(_criterion(status="skipped", criticality="warning"))
        assert not is_actionable(_criterion(status="success", criticality="pass"))

    def test_actionable_drops_rows_only_failed_would_ship(self) -> None:
        story = _story(
            [
                _criterion(status="failed", criticality="critical"),
                _criterion(status="skipped", criticality="pass"),
                _criterion(status="unprocessable", criticality="pass"),
                _criterion(status="skipped", criticality="warning"),
            ]
        )

        only_failed = project_story(story, platform=None, only_failed=True, verbose=False)
        actionable = project_story(
            story, platform=None, only_failed=False, verbose=False, actionable=True
        )

        assert only_failed is not None and len(only_failed.criteria) == 4
        assert actionable is not None
        assert [c.status for c in actionable.criteria] == ["failed"]

    def test_actionable_drops_story_with_no_actionable_criteria(self) -> None:
        story = _story([_criterion(status="skipped", criticality="pass")])

        assert (
            project_story(story, platform=None, only_failed=False, verbose=False, actionable=True)
            is None
        )


class TestVerdictStoryIdentity:
    def test_projection_carries_user_story_id(self) -> None:
        """Scenario-level triage keys on the user story, not the run."""
        story = project_story(
            _story([_criterion(status="failed", criticality="critical")]),
            platform=None,
            only_failed=False,
            verbose=False,
        )

        assert story is not None
        assert story.user_story_id == "us-1"
        assert story.story_run_id == "run-1"

    def test_caller_supplied_name_fills_null_detail_name(self) -> None:
        """The story-run detail endpoint never populates the name, so the
        batch payload's name must win rather than leaving it null."""
        story = project_story(
            _story([_criterion(status="failed", criticality="critical")], name=None),
            platform=None,
            only_failed=False,
            verbose=False,
            user_story_name="Checkout works",
        )

        assert story is not None
        assert story.user_story_name == "Checkout works"


class TestVerboseOnlyFields:
    def test_default_projection_omits_replay_and_confidence(self) -> None:
        story = project_story(
            _story([_criterion(status="failed", criticality="critical")]),
            platform=None,
            only_failed=False,
            verbose=False,
        )

        assert story is not None
        assert story.criteria[0].confidence is None
        platform = story.platforms[0]
        assert platform.build_id is None
        assert platform.recording_path is None
        assert platform.session_paths is None
        # Triage counters stay put — only replay detail is withheld.
        assert platform.platform == "ios"

    def test_verbose_restores_replay_and_confidence(self) -> None:
        story = project_story(
            _story([_criterion(status="failed", criticality="critical")]),
            platform=None,
            only_failed=False,
            verbose=True,
        )

        assert story is not None
        assert story.criteria[0].confidence == 90
        platform = story.platforms[0]
        assert platform.build_id == str(_BUILD_ID)
        assert platform.recording_path == "rec/ios.mp4"
        assert platform.session_paths == ["sess/ios.json"]
