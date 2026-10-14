"""Behavior tests for `minitest issues get`."""

import json
from pathlib import Path
from unittest.mock import patch

import httpx
from tests._commit_transport import make_settings, routed
from typer.testing import CliRunner

from minitest_cli.main import app

runner = CliRunner()
APP_ID = "a0d9820f-5136-4f70-b46b-e5966f56bfb5"
ISSUE_ID = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
FOREIGN_ISSUE_ID = "ffffffff-ffff-4fff-8fff-ffffffffffff"
BATCH_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
RUN_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
RESOLVED_FAILURE = {
    "id": ISSUE_ID,
    "status": "resolved",
    "issueStatus": "fixed",
    "criticality": "critical",
    "platform": "ios",
    "findingTitle": "Checkout button does nothing",
    "failReason": "Tapping Pay left the cart unchanged.",
    "userStoryName": "Checkout",
    "storyRunId": RUN_ID,
    "batchId": BATCH_ID,
    "rcaPrompt": "Wire the Pay button to submitOrder().",
    "webappIssueUrl": f"https://dev.minitap.ai/issues?issueId={ISSUE_ID}",
}
BATCH = {
    "id": BATCH_ID,
    "appId": APP_ID,
    "tenantId": "tenant",
    "source": "api",
    "status": "completed",
    "commitSha": None,
    "createdAt": "2026-10-14T09:30:00Z",
    "targets": [
        {
            "id": "target",
            "platform": "ios",
            "label": "iOS",
            "buildContext": {"appVersion": "4.2.0", "buildNumber": "317"},
        }
    ],
}


def _handler(request: httpx.Request) -> httpx.Response:
    routes = {
        f"/api/v1/apps/{APP_ID}/failures/{ISSUE_ID}": RESOLVED_FAILURE,
        f"/api/v1/apps/{APP_ID}/batches/{BATCH_ID}": BATCH,
    }
    payload = routes.get(request.url.path)
    if payload is None:
        return httpx.Response(404, json={"message": "Failure not found"})
    return httpx.Response(200, json=payload)


def _invoke(tmp_path: Path, issue_id: str):
    with (
        routed(_handler),
        patch("minitest_cli.main.get_settings", return_value=make_settings(tmp_path)),
        patch("minitest_cli.main.check_for_updates"),
    ):
        return runner.invoke(app, ["issues", "get", issue_id])


class TestIssuesGet:
    def test_get_returns_a_resolved_issue_with_its_build_provenance(self, tmp_path: Path) -> None:
        result = _invoke(tmp_path, ISSUE_ID)

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["issue"]["id"] == ISSUE_ID
        assert payload["issue"]["status"] == "resolved"
        assert payload["issue"]["title"] == "Checkout button does nothing"
        assert payload["issue"]["fixPrompt"] == "Wire the Pay button to submitOrder()."
        assert payload["issue"]["lastSeenBatchId"] == BATCH_ID
        assert payload["build"]["summary"] == "observed on version 4.2.0 (build 317)"

    def test_get_an_issue_of_another_app_is_not_found(self, tmp_path: Path) -> None:
        result = _invoke(tmp_path, FOREIGN_ISSUE_ID)

        assert result.exit_code == 4
        assert "not found" in result.stderr
        assert result.stdout == ""
