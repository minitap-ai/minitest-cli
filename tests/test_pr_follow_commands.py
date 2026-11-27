"""`minitest pr`: resume and polling, NDJSON, GitHub Actions, and the follow-up commands."""

import json
from pathlib import Path

import httpx
import pytest

from tests.pr_backend import (
    ANDROID_BUILD,
    BY_PR,
    CHECK_ID,
    CREATE,
    EVENTS,
    MARKDOWN,
    REPORT,
    PLAN,
    REPORT_URL,
    created,
    happy,
    invoke,
    report,
    sse,
    stream,
)

FIRST_HALF = sse(
    ("pr_check.state", {"state": "preparing", "push": 1}),
    ("pr_check.plan", {"checks": PLAN}),
    ("pr_check.item", {"checkId": "c2", "platform": "ios", "verdict": "passed", "at": 10}),
)
# What a server resuming after event 3 might send: event 3 again, then the rest.
SECOND_HALF = sse(
    ("pr_check.item", {"checkId": "c2", "platform": "ios", "verdict": "passed", "at": 10}),
    ("pr_check.item", {"checkId": "c1", "platform": "ios", "verdict": "critical", "at": 72}),
    ("pr_check.verdict", {"push": 1, "verdict": "not_ready", "counts": {}}),
    start=3,
)
RESTAURANTS_LINE = "✓ [ios]      passed     Home still lists restaurants @ 0:10"


@pytest.fixture
def context(tmp_path: Path) -> Path:
    path = tmp_path / "pr.md"
    path.write_text("Add a heart on each restaurant card.")
    return path


def check_args(context: Path, *extra: str) -> list[str]:
    return [
        "pr", "check", "--pr", "1482", "--title", "Favourites",
        "--context-file", str(context), "--android-build", ANDROID_BUILD, *extra,
    ]  # fmt: skip


class TestResilience:
    def test_dropped_stream_resumes_from_the_last_event_without_repeating(self, context):
        backend = happy("not_ready").on(EVENTS, stream(FIRST_HALF, fail=True), stream(SECOND_HALF))

        result = invoke(backend, check_args(context))

        assert result.exit_code == 1, result.output
        resumed = backend.sent(EVENTS)[1]
        assert resumed.headers["Last-Event-ID"] == "3"
        assert result.stderr.count(RESTAURANTS_LINE) == 1

    def test_a_replayed_earlier_push_is_not_printed(self, context):
        push_2 = httpx.Response(200, json=created(push=2))
        old_item = {"checkId": "c1", "platform": "ios", "verdict": "critical", "push": 1}
        new_item = {"checkId": "c2", "platform": "ios", "verdict": "passed", "at": 10, "push": 2}
        replay = sse(
            ("pr_check.state", {"state": "exploring", "push": 1}),
            ("pr_check.item", old_item),
            ("pr_check.question", {"checkId": "c2", "ask": "Old question?", "options": []}),
            ("pr_check.state", {"state": "preparing", "push": 2}),
            ("pr_check.plan", {"checks": PLAN, "push": 2}),
            ("pr_check.item", new_item),
            ("pr_check.verdict", {"push": 2, "verdict": "ready", "counts": {}}),
        )
        backend = happy().on(CREATE, push_2).on(EVENTS, stream(replay))
        backend.on(REPORT, httpx.Response(200, json=report("ready", push=2)))

        result = invoke(backend, check_args(context))

        assert result.exit_code == 0, result.output
        assert "Old question?" not in result.stderr
        assert "critical" not in result.stderr
        assert result.stderr.count(RESTAURANTS_LINE) == 1

    def test_without_a_stream_the_report_is_polled_to_the_verdict(self, context):
        unavailable = httpx.Response(503, json={"detail": "busy"})
        running = httpx.Response(200, json=report(None, state="exploring"))
        done = httpx.Response(200, json=report("ready_with_warnings"))
        backend = happy().on(EVENTS, unavailable).on(REPORT, running, done)

        result = invoke(backend, check_args(context, "--fail-on", "warning"))

        assert result.exit_code == 1, result.output
        assert result.stderr.count(RESTAURANTS_LINE) == 1
        assert "warning" in result.stderr

    def test_heartbeat_line_while_nothing_happens(self, context, monkeypatch):
        monkeypatch.setattr("minitest_cli.commands.pr_progress.HEARTBEAT_SECONDS", 0.2)
        quiet = sse(("pr_check.state", {"state": "exploring", "push": 1}))
        backend = happy().on(EVENTS, stream(quiet, hang=True))

        result = invoke(backend, check_args(context, "--timeout", "1"))

        assert "… still exploring (0m00s, 0 result(s) in)" in result.stderr


class TestMachineOutput:
    def test_json_prints_one_parseable_event_per_line(self, context):
        result = invoke(happy("not_ready"), ["--json", *check_args(context)])

        lines = [json.loads(line) for line in result.stdout.splitlines()]
        assert lines[0]["type"] == "pr_check.created"
        assert lines[0]["data"]["reportUrl"] == REPORT_URL
        assert [line["type"] for line in lines[1:3]] == ["pr_check.state", "pr_check.plan"]
        assert lines[-1]["type"] == "pr_check.result"
        assert lines[-1]["data"]["exitCode"] == 1

    def test_github_actions_gets_groups_errors_and_the_summary(
        self, context, tmp_path, monkeypatch
    ):
        summary = tmp_path / "summary.md"
        summary.write_text("# Earlier step\n")
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

        result = invoke(happy("not_ready"), check_args(context))

        assert result.exit_code == 1
        groups = [line for line in result.stderr.splitlines() if line.startswith("::")]
        assert groups == [
            "::group::Prepare", "::endgroup::", "::group::Explore & verify", "::endgroup::"
        ]  # fmt: skip
        assert "::error title=Favourite heart on each card (ios)::No heart" in result.stdout
        assert summary.read_text() == f"# Earlier step\n## Verdict: not_ready\n\n{REPORT_URL}\n"


class TestFollowUps:
    def test_wait_on_a_finished_check_exits_with_its_verdict_at_once(self):
        answer = httpx.Response(200, json=report("needs_answer"))
        backend = happy().on(BY_PR, answer).on(REPORT, answer)

        result = invoke(backend, ["pr", "wait", "1482"])

        assert result.exit_code == 2
        assert backend.sent(EVENTS) == []
        assert "clarify it in the PR text and run `minitest pr check` again" in result.stderr

    def test_wait_for_an_unknown_pr_exits_3(self):
        missing = httpx.Response(404, json={"detail": "No PR check for PR #1482."})

        result = invoke(happy().on(BY_PR, missing), ["pr", "wait", "1482"])

        assert result.exit_code == 3
        assert "No PR check for PR #1482." in result.output

    def test_report_prints_the_markdown_of_the_asked_push(self):
        backend = happy().on(BY_PR, httpx.Response(200, json=report("ready", push=2)))

        result = invoke(backend, ["pr", "report", "1482", "--push", "1"])

        assert result.exit_code == 0
        assert result.stdout == f"## Verdict: ready\n\n{REPORT_URL}\n"
        assert backend.sent(MARKDOWN)[0].url.params["push"] == "1"

    @pytest.mark.parametrize(
        ("outcome", "says"),
        [
            ("merged", "1 suite change(s) applied, 1 unproven dropped; 1 deletion(s) wait"),
            ("closed", "3 proposed change(s) discarded; the suite is unchanged."),
        ],
    )
    def test_merged_and_closed_report_the_suite_changes(self, outcome, says):
        changes = [
            {"kind": "edited", "proven": True},
            {"kind": "new", "proven": False},
            {"kind": "deleted", "proven": True},
        ]
        reply = httpx.Response(200, json={"state": outcome, "suiteChanges": changes})
        route = f"POST /api/v1/pr-checks/{CHECK_ID}/{outcome}"
        backend = happy().on(BY_PR, httpx.Response(200, json=report("ready"))).on(route, reply)

        result = invoke(backend, ["pr", outcome, "1482"])

        assert result.exit_code == 0, result.output
        assert len(backend.sent(route)) == 1
        assert says in result.stderr
