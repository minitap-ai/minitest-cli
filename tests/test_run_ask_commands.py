"""`minitest run ask`: the questions Mini asks during a run, and the run status they cause."""

import json

import httpx
import pytest

from tests.triage_backend import APP_PATH, ASK_ID, BATCH_ID, Backend, invoke

LIST = "/api/v1/escalations"
ONE = f"{LIST}/{ASK_ID}"
OTHER_ID = "eeeeeeee-0000-0000-0000-000000000002"


def escalation(**overrides) -> dict:
    body = {
        "id": ASK_ID,
        "batchId": BATCH_ID,
        "state": "awaiting_answer",
        "answerable": True,
        "answerType": "text",
        "question": "How should Mini simulate a completed rewarded-ad watch?",
        "affectedPlatforms": ["android"],
        "diagnosis": {"summary": "The ad never confirms", "proposedFix": None},
        "proposal": None,
        "proposalStatus": None,
    }
    return body | overrides


def _backend(*escalations: dict) -> Backend:
    rows = list(escalations) or [escalation()]
    return (
        Backend()
        .conductor("GET", LIST, httpx.Response(200, json={"escalations": rows}))
        .conductor("GET", ONE, httpx.Response(200, json=rows[0]))
    )


class TestAskList:
    def test_list_shows_only_questions_waiting_for_the_caller(self):
        closed = escalation(id=OTHER_ID, state="resolved")
        minitap_side = escalation(id=OTHER_ID, answerable=False)
        backend = _backend(escalation(), closed, minitap_side)

        result = invoke(backend, ["--json", "run", "ask", "list", BATCH_ID])

        assert result.exit_code == 0, result.output
        assert [e["id"] for e in json.loads(result.stdout)] == [ASK_ID]
        [request] = backend.requests
        assert request.url.params["batchId"] == BATCH_ID

    def test_list_all_includes_closed_questions(self):
        backend = _backend(escalation(), escalation(id=OTHER_ID, state="resolved"))

        result = invoke(backend, ["--json", "run", "ask", "list", BATCH_ID, "--all"])

        assert result.exit_code == 0, result.output
        assert len(json.loads(result.stdout)) == 2

    def test_list_rejects_a_non_uuid_batch(self):
        result = invoke(Backend(), ["run", "ask", "list", "not-a-uuid"])

        assert result.exit_code == 1


class TestAskWrites:
    def test_answer_posts_the_text_and_shows_the_question_again(self):
        backend = _backend().conductor("POST", f"{ONE}/answer", httpx.Response(204))

        result = invoke(
            backend, ["--json", "run", "ask", "answer", ASK_ID, "--answer", "Use the test ad unit."]
        )

        assert result.exit_code == 0, result.output
        assert backend.sent("POST", f"{ONE}/answer") == [
            {"answer": "Use the test ad unit.", "answeredVia": "webapp"}
        ]

    def test_answer_reads_stdin(self):
        backend = _backend().conductor("POST", f"{ONE}/answer", httpx.Response(204))

        result = invoke(
            backend, ["run", "ask", "answer", ASK_ID, "--answer-file", "-"], stdin="From stdin\n"
        )

        assert result.exit_code == 0, result.output
        assert backend.sent("POST", f"{ONE}/answer")[0]["answer"] == "From stdin\n"

    def test_answer_refuses_a_file_question(self):
        backend = _backend(escalation(answerType="file"))

        result = invoke(backend, ["run", "ask", "answer", ASK_ID, "--answer", "here"])

        assert result.exit_code == 1
        assert backend.sent("POST", f"{ONE}/answer") == []

    def test_answer_on_a_closed_question_exits_conflict(self):
        reply = httpx.Response(409, json={"detail": "Escalation is not awaiting an answer"})
        backend = _backend().conductor("POST", f"{ONE}/answer", reply)

        result = invoke(backend, ["run", "ask", "answer", ASK_ID, "--answer", "late"])

        assert result.exit_code == 6
        assert "run ask get" in result.output

    @pytest.mark.parametrize(
        ("command", "suffix", "body"),
        [
            (
                ["decline", ASK_ID, "--reason", "No such account"],
                "/decline",
                {"reason": "No such account"},
            ),
            (["approve", ASK_ID], "/proposal/approve", None),
            (["reject", ASK_ID], "/proposal/reject", {"reason": None}),
        ],
    )
    def test_decline_approve_reject_hit_their_route(self, command, suffix, body):
        backend = _backend().conductor("POST", f"{ONE}{suffix}", httpx.Response(204))

        result = invoke(backend, ["--json", "run", "ask", *command])

        assert result.exit_code == 0, result.output
        assert backend.sent("POST", f"{ONE}{suffix}") == [body]


class TestEscalatedRun:
    RUN_ID = "cccccccc-0000-0000-0000-000000000001"

    def _run(self) -> dict:
        return {
            "id": self.RUN_ID,
            "userStoryId": "dddddddd-0000-0000-0000-000000000001",
            "batchId": BATCH_ID,
            "createdAt": "2026-10-29T10:00:00Z",
            "platforms": [{"platform": "android", "executionState": "escalated"}],
        }

    def test_status_reports_escalated_and_points_at_the_question(self):
        backend = Backend().on(
            "GET", f"{APP_PATH}/story-runs/{self.RUN_ID}", httpx.Response(200, json=self._run())
        )

        result = invoke(backend, ["run", "status", self.RUN_ID, "--watch"])

        assert result.exit_code == 0, result.output
        assert "escalated" in result.output
        assert f"run ask list {BATCH_ID}" in " ".join(result.output.split())

    @pytest.mark.real_question_count
    def test_batch_get_counts_waiting_questions(self):
        batch = {
            "id": BATCH_ID,
            "appId": "aaaaaaaa-0000-0000-0000-000000000001",
            "tenantId": "ffffffff-0000-0000-0000-000000000001",
            "status": "running",
            "source": "manual",
            "createdAt": "2026-10-29T10:00:00Z",
            "targets": [],
            "storyRuns": [self._run()],
        }
        backend = _backend().on(
            "GET", f"{APP_PATH}/batches/{BATCH_ID}", httpx.Response(200, json=batch)
        )

        result = invoke(backend, ["--json", "batch", "get", BATCH_ID])

        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["waitingQuestions"] == 1
