"""Behavioral tests for `minitest issues fix`."""

import json
from unittest.mock import patch

import httpx
from typer.testing import CliRunner

from minitest_cli.core.config import Settings
from minitest_cli.main import app

runner = CliRunner()
_ISSUE_A = "11111111-1111-1111-1111-111111111111"
_ISSUE_B = "22222222-2222-2222-2222-222222222222"


class _FakeApiClient:
    responses: dict[str, httpx.Response] = {}
    requests: list[tuple[str, dict[str, str]]] = []

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        return None

    async def patch(self, path: str, **kwargs) -> httpx.Response:
        self.requests.append((path, kwargs["json"]))
        return self.responses[path]


def _invoke(issue_ids: list[str]):
    settings = Settings(token="test-token", app_id="app-123")
    with (
        patch("minitest_cli.main.get_settings", return_value=settings),
        patch("minitest_cli.main.check_for_updates"),
        patch("minitest_cli.commands.issues_fix.ApiClient", _FakeApiClient),
    ):
        return runner.invoke(app, ["issues", "fix", *issue_ids])


def _response(status_code: int, body: dict | None = None) -> httpx.Response:
    return httpx.Response(
        status_code, json=body or {}, request=httpx.Request("PATCH", "https://api")
    )


class TestIssuesFix:
    def setup_method(self) -> None:
        _FakeApiClient.requests = []
        _FakeApiClient.responses = {}

    def test_fix_multiple_ids_reports_each_success_as_json(self) -> None:
        _FakeApiClient.responses = {
            f"/api/v1/apps/app-123/failures/{_ISSUE_A}/status": _response(200),
            f"/api/v1/apps/app-123/failures/{_ISSUE_B}/status": _response(200),
        }

        result = _invoke([_ISSUE_A, _ISSUE_B])

        assert result.exit_code == 0
        assert json.loads(result.stdout) == {
            "results": [
                {"issueId": _ISSUE_A, "status": "fixed"},
                {"issueId": _ISSUE_B, "status": "fixed"},
            ],
            "fixed": 2,
            "failed": 0,
        }
        assert _FakeApiClient.requests == [
            (
                f"/api/v1/apps/app-123/failures/{_ISSUE_A}/status",
                {"issueStatus": "fixed"},
            ),
            (
                f"/api/v1/apps/app-123/failures/{_ISSUE_B}/status",
                {"issueStatus": "fixed"},
            ),
        ]

    def test_fix_partial_failure_continues_and_exits_nonzero(self) -> None:
        _FakeApiClient.responses = {
            f"/api/v1/apps/app-123/failures/{_ISSUE_A}/status": _response(
                409, {"detail": "triage_locked"}
            ),
            f"/api/v1/apps/app-123/failures/{_ISSUE_B}/status": _response(200),
        }

        result = _invoke([_ISSUE_A, _ISSUE_B])

        assert result.exit_code == 1
        assert json.loads(result.stdout) == {
            "results": [
                {
                    "issueId": _ISSUE_A,
                    "status": "failed",
                    "error": (
                        "Finding feedback is still processing. Retry after processing completes."
                    ),
                },
                {"issueId": _ISSUE_B, "status": "fixed"},
            ],
            "fixed": 1,
            "failed": 1,
        }
        assert len(_FakeApiClient.requests) == 2

    def test_fix_all_missing_exits_not_found(self) -> None:
        _FakeApiClient.responses = {
            f"/api/v1/apps/app-123/failures/{_ISSUE_A}/status": _response(
                404, {"detail": "Finding not found"}
            ),
        }

        result = _invoke([_ISSUE_A])

        assert result.exit_code == 4
        assert json.loads(result.stdout)["results"] == [
            {"issueId": _ISSUE_A, "status": "failed", "error": "Finding not found"}
        ]
