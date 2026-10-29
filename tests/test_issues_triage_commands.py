"""`minitest issues not-a-bug|archive|reopen|severity|ticket`: webapp triage from the CLI."""

import json

import httpx
import pytest

from tests.triage_backend import (
    APP_PATH,
    CRITERION_ID,
    ISSUE_ID,
    RESULT_ID,
    TAG_ID,
    Backend,
    failure,
    invoke,
)

ISSUE = f"{APP_PATH}/failures/{ISSUE_ID}"
STATUS = f"{ISSUE}/status"
AC_FEEDBACK = f"{APP_PATH}/issues/{RESULT_ID}/feedback"
FINDING_FEEDBACK = f"{ISSUE}/feedback"
TEXT = "The promo banner is expected here."


def _ok(**overrides) -> httpx.Response:
    return httpx.Response(200, json=failure(**overrides))


class TestNotABug:
    def test_criterion_issue_waits_for_processing_then_resolves(self):
        backend = (
            Backend()
            .on("GET", ISSUE, _ok(), _ok(feedbackPending=True), _ok(feedbackPending=False))
            .on("POST", AC_FEEDBACK, httpx.Response(201, json={"id": "fb"}))
            .on("PATCH", STATUS, _ok(issueStatus="fixed"))
        )

        result = invoke(backend, ["issues", "not-a-bug", ISSUE_ID, TEXT])

        assert result.exit_code == 0, result.output
        report = json.loads(result.stdout)
        assert report["closed"] is True and report["issueStatus"] == "fixed"
        assert backend.sent("POST", AC_FEEDBACK) == [{"feedbackText": TEXT}]
        assert backend.sent("PATCH", STATUS) == [{"issueStatus": "fixed"}]

    def test_status_conflict_is_retried_until_processing_is_over(self):
        conflict = httpx.Response(409, json={"detail": "Feedback is still being processed"})
        backend = (
            Backend()
            .on("GET", ISSUE, _ok())
            .on("POST", AC_FEEDBACK, httpx.Response(201, json={}))
            .on("PATCH", STATUS, conflict, _ok(issueStatus="fixed"))
        )

        result = invoke(backend, ["issues", "not-a-bug", ISSUE_ID, TEXT])

        assert result.exit_code == 0, result.output
        assert len(backend.sent("PATCH", STATUS)) == 2

    def test_finding_issue_takes_the_feedback_on_the_issue(self):
        backend = (
            Backend()
            .on("GET", ISSUE, _ok(acceptanceCriteriaResultId=None, criterionId=None))
            .on("POST", FINDING_FEEDBACK, _ok(acceptanceCriteriaResultId=None, issueStatus="fixed"))
        )

        result = invoke(backend, ["issues", "not-a-bug", ISSUE_ID, TEXT, "--scope", "app"])

        assert result.exit_code == 0, result.output
        report = json.loads(result.stdout)
        assert report["closed"] is True and report["scope"] is None
        assert "--scope ignored" in " ".join(result.output.split())
        assert backend.sent("POST", FINDING_FEEDBACK) == [
            {"feedbackText": TEXT, "scope": {"kind": "app"}}
        ]
        assert backend.sent("PATCH", STATUS) == []

    def test_tag_scope_resolves_the_tag_name(self):
        tags = httpx.Response(200, json=[{"id": TAG_ID, "name": "Checkout"}])
        backend = (
            Backend()
            .on("GET", ISSUE, _ok())
            .on("GET", f"{APP_PATH}/tags", tags)
            .on("POST", AC_FEEDBACK, httpx.Response(201, json={}))
        )

        result = invoke(
            backend,
            ["issues", "not-a-bug", ISSUE_ID, TEXT, "--scope", "tag:checkout", "--keep-open"],
        )

        assert result.exit_code == 0, result.output
        assert backend.sent("POST", AC_FEEDBACK) == [
            {"feedbackText": TEXT, "scope": {"kind": "tag", "id": TAG_ID}}
        ]
        assert json.loads(result.stdout)["closed"] is False
        assert backend.sent("PATCH", STATUS) == []

    def test_bad_scope_fails_before_any_request(self):
        backend = Backend()

        result = invoke(backend, ["issues", "not-a-bug", ISSUE_ID, TEXT, "--scope", "tenant"])

        assert result.exit_code == 1
        assert backend.requests == []

    def test_timeout_keeps_the_feedback_and_exits_nonzero(self):
        backend = (
            Backend()
            .on("GET", ISSUE, _ok(), _ok(feedbackPending=True))
            .on("POST", AC_FEEDBACK, httpx.Response(201, json={}))
        )

        result = invoke(backend, ["issues", "not-a-bug", ISSUE_ID, TEXT, "--timeout", "0"])

        assert result.exit_code == 1
        assert json.loads(result.stdout)["timedOut"] is True
        assert "issues fix" in result.output


class TestRunFeedbackScope:
    def test_run_feedback_sends_the_scope(self):
        backend = Backend().on("POST", AC_FEEDBACK, httpx.Response(201, json={}))

        result = invoke(backend, ["run", "feedback", RESULT_ID, TEXT, "--scope", "scenario"])

        assert result.exit_code == 0, result.output
        assert backend.sent("POST", AC_FEEDBACK) == [
            {"feedbackText": TEXT, "scope": {"kind": "scenario"}}
        ]


class TestStatusCommands:
    @pytest.mark.parametrize(
        ("command", "server_status", "label"),
        [("archive", "acknowledged", "archived"), ("reopen", "review", "open")],
    )
    def test_status_commands_send_the_webapp_status(self, command, server_status, label):
        backend = Backend().on("PATCH", STATUS, _ok(issueStatus=server_status))

        result = invoke(backend, ["issues", command, ISSUE_ID])

        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout) == {
            "results": [{"issueId": ISSUE_ID, "status": label}],
            label: 1,
            "failed": 0,
        }
        assert backend.sent("PATCH", STATUS) == [{"issueStatus": server_status}]


class TestSeverity:
    SEVERITY = f"{APP_PATH}/criteria/{CRITERION_ID}/severity-override"

    @pytest.mark.parametrize(("level", "override"), [("warning", "warning"), ("reset", None)])
    def test_severity_patches_the_criterion_override(self, level, override):
        backend = (
            Backend()
            .on("GET", ISSUE, _ok())
            .on("PATCH", self.SEVERITY, _ok(criticality="warning", severityOverride=override))
        )

        result = invoke(backend, ["issues", "severity", ISSUE_ID, level])

        assert result.exit_code == 0, result.output
        assert backend.sent("PATCH", self.SEVERITY) == [{"override": override}]
        assert json.loads(result.stdout)["resultId"] == RESULT_ID

    def test_severity_refuses_an_issue_without_criterion(self):
        backend = Backend().on("GET", ISSUE, _ok(criterionId=None))

        result = invoke(backend, ["issues", "severity", ISSUE_ID, "critical"])

        assert result.exit_code == 1
        assert backend.sent("PATCH", self.SEVERITY) == []


class TestTicket:
    def test_create_groups_repeated_fields(self):
        backend = Backend().on("POST", f"{ISSUE}/ticket", httpx.Response(201, json=failure()))

        create = ["issues", "ticket", "create", ISSUE_ID, "--provider", "linear"]
        fields = ["--field", "labels=bug", "--field", "labels=mobile", "--field", "priority=2"]

        result = invoke(backend, [*create, "--target", "team-1", *fields])

        assert result.exit_code == 0, result.output
        assert backend.sent("POST", f"{ISSUE}/ticket") == [
            {
                "provider": "linear",
                "targetId": "team-1",
                "fields": {"labels": ["bug", "mobile"], "priority": ["2"]},
            }
        ]

    def test_link_get_unlink_and_targets(self):
        backend = (
            Backend()
            .on("POST", f"{ISSUE}/ticket/link", _ok())
            .on("GET", f"{ISSUE}/ticket", httpx.Response(200, json={"linked": True}))
            .on("DELETE", f"{ISSUE}/ticket", _ok())
            .on(
                "GET",
                f"{APP_PATH}/trackers/jira/targets",
                httpx.Response(200, json={"targets": []}),
            )
        )

        link = ["issues", "ticket", "link", ISSUE_ID, "--provider", "jira", "--ticket", "QA-12"]
        assert invoke(backend, link).exit_code == 0
        assert invoke(backend, ["issues", "ticket", "get", ISSUE_ID]).exit_code == 0
        assert invoke(backend, ["issues", "ticket", "unlink", ISSUE_ID]).exit_code == 0
        assert invoke(backend, ["issues", "ticket", "targets", "jira"]).exit_code == 0
        assert backend.sent("POST", f"{ISSUE}/ticket/link") == [
            {"provider": "jira", "externalId": "QA-12"}
        ]
        assert len(backend.sent("DELETE", f"{ISSUE}/ticket")) == 1


class TestIssuesListExposesResultId:
    def test_get_returns_result_id_and_triage_fields(self):
        backend = Backend().on("GET", ISSUE, _ok(batchId=None, severityOverride="warning"))

        result = invoke(backend, ["issues", "get", ISSUE_ID])

        assert result.exit_code == 0, result.output
        issue = json.loads(result.stdout)["issue"]
        assert issue["resultId"] == RESULT_ID
        assert issue["severityOverride"] == "warning"
        assert issue["feedbackPending"] is False
