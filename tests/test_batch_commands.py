"""Tests for batch commands (list, get, cancel)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import typer
from typer.testing import CliRunner

from minitest_cli.commands.batch import app as batch_app
from minitest_cli.core.config import Settings

runner = CliRunner()


_BATCH_UUID = "99999999-8888-7777-6666-555555555555"
_RUN_UUID = "11111111-2222-3333-4444-555555555555"
_USER_STORY_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _make_settings(tmp_path, **overrides):
    defaults = {
        "config_dir": tmp_path,
        "token": "test-token",
        "supabase_url": "https://test.supabase.co",
        "supabase_publishable_key": "test-publishable-key",
        "app_id": "app-123",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _patch_context(settings, json_mode=False, app_flag=None):
    return [
        patch.object(typer.Context, "settings", settings, create=True),
        patch.object(typer.Context, "json_mode", json_mode, create=True),
        patch.object(typer.Context, "app_flag", app_flag, create=True),
    ]


def _run_with_context(args, settings, json_mode=False, app_flag=None):
    patches = _patch_context(settings, json_mode, app_flag)
    for p in patches:
        p.start()
    try:
        return runner.invoke(batch_app, args)
    finally:
        for p in patches:
            p.stop()


def _mock_response(status_code: int = 200, json_data: object = None) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = json.dumps(json_data) if json_data else ""
    return resp


def _mock_client() -> AsyncMock:
    client = AsyncMock()
    client.get = AsyncMock()
    client.post = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


_BATCH_LIST_ITEM = {
    "id": _BATCH_UUID,
    "appId": "app-123",
    "tenantId": "tenant-1",
    "source": "api",
    "status": "completed",
    "commitSha": "abc1234567890",
    "tagName": "v1.0.0",
    "appVersion": "1.0.0",
    "buildNumber": "42",
    "userStoryTypes": ["login"],
    "triggeredByUserId": None,
    "iosBuildId": None,
    "androidBuildId": None,
    "iosBuildName": None,
    "androidBuildName": None,
    "startedAt": None,
    "finishedAt": None,
    "createdAt": "2025-06-01T10:00:00Z",
    "ios": {},
    "android": {},
    "githubContext": None,
    "storyRuns": [],
}

_BATCH_LIST_RESPONSE = {
    "items": [_BATCH_LIST_ITEM],
    "total": 1,
    "page": 1,
    "pageSize": 20,
}

_BATCH_RESPONSE = {
    "id": _BATCH_UUID,
    "appId": "app-123",
    "tenantId": "tenant-1",
    "source": "api",
    "status": "running",
    "commitSha": None,
    "tagName": None,
    "triggeredByUserId": None,
    "iosBuildId": None,
    "androidBuildId": None,
    "awaitingBuildId": None,
    "startedAt": None,
    "finishedAt": None,
    "createdAt": "2025-06-01T10:00:00Z",
    "ios": {},
    "android": {},
    "githubContext": None,
    "storyRuns": [
        {
            "id": _RUN_UUID,
            "userStoryId": _USER_STORY_UUID,
            "userStoryName": "Login Story",
            "tenantId": "tenant-1",
            "status": "pending",
            "iosBuildId": None,
            "androidBuildId": None,
            "iosRecordingPath": None,
            "androidRecordingPath": None,
            "iosRecordingUrl": None,
            "androidRecordingUrl": None,
            "iosErrorMessage": None,
            "androidErrorMessage": None,
            "iosSessionPaths": [],
            "androidSessionPaths": [],
            "iosRecordingStartedAt": None,
            "androidRecordingStartedAt": None,
            "iosSegmentMap": None,
            "androidSegmentMap": None,
            "iosStatus": None,
            "androidStatus": None,
            "startedAt": None,
            "finishedAt": None,
            "createdAt": "2025-06-01T10:00:00Z",
        }
    ],
}

_CANCELLED_BATCH = {**_BATCH_RESPONSE, "status": "cancelled"}


class TestListBatchesCommand:
    def test_list_returns_table(self, tmp_path) -> None:
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.get = AsyncMock(return_value=_mock_response(200, _BATCH_LIST_RESPONSE))

        with patch("minitest_cli.commands.batch.ApiClient", return_value=client):
            result = _run_with_context(["list"], settings)

        assert result.exit_code == 0
        assert _BATCH_UUID[:8] in result.output
        assert client.get.call_args[0][0] == "/api/v1/apps/app-123/batches"

    def test_list_json_mode(self, tmp_path) -> None:
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.get = AsyncMock(return_value=_mock_response(200, _BATCH_LIST_RESPONSE))

        with patch("minitest_cli.commands.batch.ApiClient", return_value=client):
            result = _run_with_context(["list"], settings, json_mode=True)

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["total"] == 1
        assert data["items"][0]["id"] == _BATCH_UUID

    def test_list_forwards_filters(self, tmp_path) -> None:
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.get = AsyncMock(return_value=_mock_response(200, _BATCH_LIST_RESPONSE))

        with patch("minitest_cli.commands.batch.ApiClient", return_value=client):
            result = _run_with_context(
                [
                    "list",
                    "--status",
                    "running",
                    "--commit-sha",
                    "abcd1234",
                    "--search",
                    "login",
                ],
                settings,
            )

        assert result.exit_code == 0
        params = client.get.call_args[1]["params"]
        assert params["status"] == ["running"]
        assert params["commit_sha"] == "abcd1234"
        assert params["search"] == "login"

    def test_list_all_bumps_page_size(self, tmp_path) -> None:
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.get = AsyncMock(return_value=_mock_response(200, _BATCH_LIST_RESPONSE))

        with patch("minitest_cli.commands.batch.ApiClient", return_value=client):
            result = _run_with_context(["list", "--all"], settings)

        assert result.exit_code == 0
        params = client.get.call_args[1]["params"]
        assert params["page"] == 1
        assert params["page_size"] == 100

    def test_list_network_error_exits_3(self, tmp_path) -> None:
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))

        with patch("minitest_cli.commands.batch.ApiClient", return_value=client):
            result = _run_with_context(["list"], settings)

        assert result.exit_code == 3


class TestGetBatchCommand:
    def test_get_renders_batch_and_runs(self, tmp_path) -> None:
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.get = AsyncMock(return_value=_mock_response(200, _BATCH_RESPONSE))

        with patch("minitest_cli.commands.batch.ApiClient", return_value=client):
            result = _run_with_context(["get", _BATCH_UUID], settings)

        assert result.exit_code == 0
        assert _BATCH_UUID in result.output  # full UUID appears in header line
        assert _RUN_UUID[:8] in result.output
        assert client.get.call_args[0][0] == f"/api/v1/apps/app-123/batches/{_BATCH_UUID}"

    def test_get_json_mode(self, tmp_path) -> None:
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.get = AsyncMock(return_value=_mock_response(200, _BATCH_RESPONSE))

        with patch("minitest_cli.commands.batch.ApiClient", return_value=client):
            result = _run_with_context(["get", _BATCH_UUID], settings, json_mode=True)

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["id"] == _BATCH_UUID
        assert data["status"] == "running"

    def test_get_rejects_invalid_uuid(self, tmp_path) -> None:
        settings = _make_settings(tmp_path)
        result = _run_with_context(["get", "not-a-uuid"], settings)
        assert result.exit_code == 1

    def test_get_not_found_exits_4(self, tmp_path) -> None:
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.get = AsyncMock(return_value=_mock_response(404, {"detail": "Batch not found"}))

        with patch("minitest_cli.commands.batch.ApiClient", return_value=client):
            result = _run_with_context(["get", "deadbeef-dead-beef-dead-beefdeadbeef"], settings)

        assert result.exit_code == 4


class TestCancelBatchCommand:
    def test_cancel_posts_to_cancel_endpoint(self, tmp_path) -> None:
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.post = AsyncMock(return_value=_mock_response(200, _CANCELLED_BATCH))

        with patch("minitest_cli.commands.batch.ApiClient", return_value=client):
            result = _run_with_context(["cancel", _BATCH_UUID], settings)

        assert result.exit_code == 0
        assert client.post.call_args[0][0] == f"/api/v1/apps/app-123/batches/{_BATCH_UUID}/cancel"
        assert _BATCH_UUID in result.output

    def test_cancel_json_output(self, tmp_path) -> None:
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.post = AsyncMock(return_value=_mock_response(200, _CANCELLED_BATCH))

        with patch("minitest_cli.commands.batch.ApiClient", return_value=client):
            result = _run_with_context(["cancel", _BATCH_UUID], settings, json_mode=True)

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "cancelled"
        assert data["id"] == _BATCH_UUID

    def test_cancel_rejects_invalid_uuid(self, tmp_path) -> None:
        settings = _make_settings(tmp_path)
        result = _run_with_context(["cancel", "not-a-uuid"], settings)
        assert result.exit_code == 1

    def test_cancel_not_found_exits_4(self, tmp_path) -> None:
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.post = AsyncMock(return_value=_mock_response(404, {"detail": "Batch not found"}))

        with patch("minitest_cli.commands.batch.ApiClient", return_value=client):
            result = _run_with_context(["cancel", "deadbeef-dead-beef-dead-beefdeadbeef"], settings)

        assert result.exit_code == 4

    def test_cancel_requires_auth(self, tmp_path) -> None:
        settings = _make_settings(tmp_path, token=None)

        with patch(
            "minitest_cli.core.auth.require_auth",
            side_effect=typer.Exit(code=2),
        ):
            result = _run_with_context(["cancel", _BATCH_UUID], settings)

        assert result.exit_code == 2
