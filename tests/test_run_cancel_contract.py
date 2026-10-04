"""Cancellation uses the server's target routes, never a batch fallback."""

import copy
import json
from unittest.mock import AsyncMock, patch

import pytest

from tests.test_run_commands import (
    _make_settings,
    _mock_client,
    _mock_response,
    _PENDING_RUN,
    _RUN_UUID,
    _run_with_context,
)

SRP_ONE = "aaaaaaaa-1111-1111-1111-111111111111"
SRP_TWO = "bbbbbbbb-2222-2222-2222-222222222222"


def run_payload(states: tuple[str, str] = ("running", "pending")) -> dict:
    body = copy.deepcopy(_PENDING_RUN)
    for target, srp, state in zip(body["platforms"], (SRP_ONE, SRP_TWO), states, strict=True):
        target.update(srpId=srp, platform="web", executionState=state)
    return body


def contract_client(body: dict):
    client = _mock_client()
    client.get = AsyncMock(side_effect=lambda *_: _mock_response(200, body))

    async def post(path):
        for target in body["platforms"]:
            if path == f"/api/v1/apps/app-123/story-run-platforms/{target.get('srpId')}/cancel":
                target["cancellationRequestedAt"] = "2025-06-01T10:00:30Z"
                return _mock_response(200, body)
        return _mock_response(404, {"message": "Not Found"})

    client.post = AsyncMock(side_effect=post)
    return client


def invoke(tmp_path, client):
    with patch("minitest_cli.commands.run.ApiClient", return_value=client):
        return _run_with_context(["cancel", _RUN_UUID], _make_settings(tmp_path), json_mode=True)


class TestRunCancelContract:
    def test_finished_run_is_read_only_and_not_reported_as_cancelled(self, tmp_path):
        body = run_payload(("completed", "escalated"))
        client = contract_client(body)
        with patch("minitest_cli.commands.run.ApiClient", return_value=client):
            result = _run_with_context(["cancel", _RUN_UUID], _make_settings(tmp_path))
        assert result.exit_code == 0, result.output
        assert "No active targets to cancel" in result.output
        assert "Cancellation requested" not in result.output
        client.post.assert_not_awaited()

    def test_cancels_each_requested_run_target_using_supported_routes(self, tmp_path):
        body = run_payload()
        client = contract_client(body)
        result = invoke(tmp_path, client)
        assert result.exit_code == 0, result.output
        assert [call.args[0] for call in client.post.call_args_list] == [
            f"/api/v1/apps/app-123/story-run-platforms/{srp}/cancel" for srp in (SRP_ONE, SRP_TWO)
        ]
        assert all(
            target["cancellationRequestedAt"] for target in json.loads(result.output)["platforms"]
        )

    @pytest.mark.parametrize("state", ["completed", "failed", "skipped", "escalated", "evaluating"])
    def test_preserves_finished_target_and_cancels_active_sibling(self, tmp_path, state):
        body = run_payload((state, "running"))
        client = contract_client(body)
        result = invoke(tmp_path, client)
        assert result.exit_code == 0, result.output
        client.post.assert_awaited_once_with(
            f"/api/v1/apps/app-123/story-run-platforms/{SRP_TWO}/cancel"
        )
        assert json.loads(result.output)["platforms"][0]["cancellationRequestedAt"] is None

    def test_missing_active_target_id_refuses_before_any_write(self, tmp_path):
        body = run_payload()
        del body["platforms"][1]["srpId"]
        client = contract_client(body)
        result = invoke(tmp_path, client)
        assert result.exit_code == 3
        assert "target ID" in result.output
        client.post.assert_not_awaited()

    def test_already_cancelled_target_is_not_posted_again(self, tmp_path):
        body = run_payload()
        body["platforms"][0]["cancellationRequestedAt"] = "2025-06-01T10:00:30Z"
        client = contract_client(body)
        result = invoke(tmp_path, client)
        assert result.exit_code == 0, result.output
        client.post.assert_awaited_once_with(
            f"/api/v1/apps/app-123/story-run-platforms/{SRP_TWO}/cancel"
        )

    def test_completion_race_refreshes_without_cancelling_finished_target(self, tmp_path):
        body = run_payload()
        client = contract_client(body)
        normal_post = client.post.side_effect

        async def race(path):
            if SRP_ONE in path:
                body["platforms"][0]["executionState"] = "completed"
                return _mock_response(409, {"message": "Platform cannot be cancelled"})
            return await normal_post(path)

        client.post.side_effect = race
        result = invoke(tmp_path, client)
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["platforms"][0]["executionState"] == "completed"
        assert json.loads(result.output)["platforms"][0]["cancellationRequestedAt"] is None

    def test_nonterminal_conflict_is_reported_without_batch_fallback(self, tmp_path):
        body = run_payload()
        client = contract_client(body)
        client.post.side_effect = lambda *_: _mock_response(409, {"message": "Conflict"})
        result = invoke(tmp_path, client)
        assert result.exit_code == 3
        assert "Conflict" in result.output
        assert len(client.post.call_args_list) == 1
