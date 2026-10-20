"""`minitest draft link-pr|unlink-pr` and `draft check --again`."""

import json
from unittest.mock import AsyncMock, patch

import httpx

from tests.draft_backend import DRAFT_ID, Backend, draft, invoke

ONE = f"/api/v1/drafts/{DRAFT_ID}"
PR = f"{ONE}/pr"
LINKED = draft(state="waiting", linkedPr={"number": 42, "repo": "acme/shop"})


class TestLinkPr:
    def test_link_pr_sends_number_and_repo(self):
        backend = Backend().on("PUT", PR, httpx.Response(200, json=LINKED))

        result = invoke(
            backend, ["--json", "draft", "link-pr", DRAFT_ID, "42", "--repo", "acme/shop"]
        )

        assert result.exit_code == 0, result.output
        assert backend.sent("PUT", PR) == [{"number": 42, "repo": "acme/shop"}]
        assert json.loads(result.stdout)["linkedPr"] == {"number": 42, "repo": "acme/shop"}

    def test_link_pr_without_repo_lets_conductor_pick_the_app_repo(self):
        backend = Backend().on("PUT", PR, httpx.Response(200, json=LINKED))

        result = invoke(backend, ["draft", "link-pr", DRAFT_ID, "42"])

        assert result.exit_code == 0, result.output
        assert backend.sent("PUT", PR) == [{"number": 42}]
        assert "acme/shop#42" in result.stdout

    def test_link_pr_unknown_pr_exits_not_found(self):
        missing = httpx.Response(404, json={"detail": "No pull request #9 on acme/shop."})
        backend = Backend().on("PUT", PR, missing)

        result = invoke(backend, ["draft", "link-pr", DRAFT_ID, "9"])

        assert result.exit_code == 4
        assert "No pull request #9" in result.output

    def test_link_pr_on_ticket_draft_exits_conflict(self):
        refused = httpx.Response(409, json={"detail": "This draft already follows its ticket."})
        backend = Backend().on("PUT", PR, refused)

        result = invoke(backend, ["draft", "link-pr", DRAFT_ID, "9"])

        assert result.exit_code == 6

    def test_link_pr_rejects_non_positive_number(self):
        result = invoke(Backend(), ["draft", "link-pr", DRAFT_ID, "0"])

        assert result.exit_code == 2

    def test_unlink_pr_deletes_the_link(self):
        backend = Backend().on("DELETE", PR, httpx.Response(200, json=draft()))

        result = invoke(backend, ["--json", "draft", "unlink-pr", DRAFT_ID])

        assert result.exit_code == 0, result.output
        assert len(backend.sent("DELETE", PR)) == 1
        assert "linkedPr" not in json.loads(result.stdout)


class TestCheckAgain:
    def test_check_again_asks_for_a_full_rewalk(self):
        backend = Backend().on("POST", f"{ONE}/check", httpx.Response(200, json=LINKED))

        result = invoke(backend, ["--json", "draft", "check", DRAFT_ID, "--again"])

        assert result.exit_code == 0, result.output
        assert backend.sent("POST", f"{ONE}/check") == [{"includeWaiting": False, "again": True}]

    def test_check_without_again_does_not_send_it(self):
        backend = Backend().on("POST", f"{ONE}/check", httpx.Response(200, json=LINKED))

        result = invoke(backend, ["--json", "draft", "check", DRAFT_ID])

        assert result.exit_code == 0, result.output
        assert backend.sent("POST", f"{ONE}/check") == [{"includeWaiting": False}]


class TestWatchBuild:
    def _waiting(self, status: str) -> dict:
        build = {"status": status, "commitSha": "b0381df", "etaSeconds": 300}
        return draft(state="waiting", stateReasonCode="waiting_build", waitingFor={"build": build})

    def test_watch_settled_waits_for_the_pr_head_build(self):
        backend = Backend().on(
            "GET",
            ONE,
            httpx.Response(200, json=self._waiting("requested")),
            httpx.Response(200, json=self._waiting("building")),
            httpx.Response(200, json=draft(state="ready", stateReasonCode=None)),
        )

        with patch("minitest_cli.commands.draft_watch.asyncio.sleep", AsyncMock()):
            result = invoke(
                backend, ["--json", "draft", "get", DRAFT_ID, "--watch", "--until", "settled"]
            )

        assert result.exit_code == 0, result.output
        assert len(backend.sent("GET", ONE)) == 3
        assert json.loads(result.stdout)["state"] == "ready"

    def test_watch_settled_stops_on_a_failed_build(self):
        backend = Backend().on("GET", ONE, httpx.Response(200, json=self._waiting("failed")))

        result = invoke(
            backend, ["--json", "draft", "get", DRAFT_ID, "--watch", "--until", "settled"]
        )

        assert result.exit_code == 0, result.output
        assert len(backend.sent("GET", ONE)) == 1


class TestRejectedKey:
    def test_revoked_key_exits_auth_failure_not_network(self):
        refused = httpx.Response(401, json={"detail": "Invalid minitest API key"})
        backend = Backend(apps_reply=refused)

        result = invoke(backend, ["draft", "list"])

        assert result.exit_code == 1
        assert "Authentication failed (401): Invalid minitest API key" in result.output

    def test_testing_service_outage_still_exits_network(self):
        backend = Backend(apps_reply=httpx.Response(503, text="down"))

        result = invoke(backend, ["draft", "list"])

        assert result.exit_code == 3
