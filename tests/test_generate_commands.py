"""Tests for generation-job commands (start, status, list)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import typer
from typer.testing import CliRunner

from minitest_cli.commands.generate import app as generate_app
from minitest_cli.core.config import Settings

runner = CliRunner()

_JOB_UUID = "aaaaaaaa-bbbb-cccc-dddd-111111111111"


def _make_settings(tmp_path, **overrides):
    defaults = {
        "config_dir": tmp_path,
        "token": "test-token",
        "supabase_url": "https://test.supabase.co",
        "supabase_publishable_key": "test-key",
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
        return runner.invoke(generate_app, args)
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


_JOB_RESPONSE = {
    "id": _JOB_UUID,
    "appId": "app-123",
    "tenantId": "tenant-1",
    "status": "running",
    "repoOwner": "acme",
    "repoName": "mobile-app",
    "repoRef": "main",
    "userStoriesCreated": 5,
    "createdAt": "2026-05-23T10:00:00Z",
}

_JOB_DETAIL = {
    **_JOB_RESPONSE,
    "statusUpdates": [
        {
            "id": "upd-1",
            "category": "exploring",
            "message": "Scanning project structure",
            "createdAt": "2026-05-23T10:01:00Z",
        },
    ],
}

_JOB_LIST_RESPONSE = {
    "items": [_JOB_RESPONSE],
    "total": 1,
    "page": 1,
    "pageSize": 20,
}


class TestStartGeneration:
    def test_start_posts_to_api(self, tmp_path) -> None:
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.post = AsyncMock(return_value=_mock_response(200, _JOB_RESPONSE))

        with patch("minitest_cli.commands.generate.ApiClient", return_value=client):
            result = _run_with_context(
                ["start", "--repo-owner", "acme", "--repo-name", "mobile-app"],
                settings,
            )

        assert result.exit_code == 0
        assert _JOB_UUID in result.output
        call_args = client.post.call_args
        assert call_args[0][0] == "/api/v1/apps/app-123/generation-jobs"
        payload = call_args[1]["json"]
        assert payload["repoOwner"] == "acme"
        assert payload["repoName"] == "mobile-app"
        assert payload["repoRef"] == "main"

    def test_start_json_mode(self, tmp_path) -> None:
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.post = AsyncMock(return_value=_mock_response(200, _JOB_RESPONSE))

        with patch("minitest_cli.commands.generate.ApiClient", return_value=client):
            result = _run_with_context(
                ["start", "--repo-owner", "acme", "--repo-name", "mobile-app"],
                settings,
                json_mode=True,
            )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["id"] == _JOB_UUID

    def test_start_custom_ref(self, tmp_path) -> None:
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.post = AsyncMock(return_value=_mock_response(200, _JOB_RESPONSE))

        with patch("minitest_cli.commands.generate.ApiClient", return_value=client):
            result = _run_with_context(
                [
                    "start",
                    "--repo-owner",
                    "acme",
                    "--repo-name",
                    "mobile-app",
                    "--ref",
                    "develop",
                ],
                settings,
            )

        assert result.exit_code == 0
        assert client.post.call_args[1]["json"]["repoRef"] == "develop"

    def test_start_feature_disabled_exits_1(self, tmp_path) -> None:
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.post = AsyncMock(
            return_value=_mock_response(403, {"detail": "Story generation is disabled"})
        )

        with patch("minitest_cli.commands.generate.ApiClient", return_value=client):
            result = _run_with_context(
                ["start", "--repo-owner", "acme", "--repo-name", "mobile-app"],
                settings,
            )

        assert result.exit_code == 1

    def test_start_conflict_exits_1(self, tmp_path) -> None:
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.post = AsyncMock(return_value=_mock_response(409, {"detail": "Already running"}))

        with patch("minitest_cli.commands.generate.ApiClient", return_value=client):
            result = _run_with_context(
                ["start", "--repo-owner", "acme", "--repo-name", "mobile-app"],
                settings,
            )

        assert result.exit_code == 1


class TestGetGenerationStatus:
    def test_status_shows_details(self, tmp_path) -> None:
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.get = AsyncMock(return_value=_mock_response(200, _JOB_DETAIL))

        with patch("minitest_cli.commands.generate.ApiClient", return_value=client):
            result = _run_with_context(["status", _JOB_UUID], settings)

        assert result.exit_code == 0
        assert _JOB_UUID in result.output
        assert "exploring" in result.output.lower() or "Scanning" in result.output

    def test_status_json_mode(self, tmp_path) -> None:
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.get = AsyncMock(return_value=_mock_response(200, _JOB_DETAIL))

        with patch("minitest_cli.commands.generate.ApiClient", return_value=client):
            result = _run_with_context(["status", _JOB_UUID], settings, json_mode=True)

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["id"] == _JOB_UUID
        assert len(data["statusUpdates"]) == 1

    def test_status_not_found_exits_4(self, tmp_path) -> None:
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.get = AsyncMock(return_value=_mock_response(404, {"detail": "Not found"}))

        with patch("minitest_cli.commands.generate.ApiClient", return_value=client):
            result = _run_with_context(["status", _JOB_UUID], settings)

        assert result.exit_code == 4


class TestListGenerationJobs:
    def test_list_shows_table(self, tmp_path) -> None:
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.get = AsyncMock(return_value=_mock_response(200, _JOB_LIST_RESPONSE))

        with patch("minitest_cli.commands.generate.ApiClient", return_value=client):
            result = _run_with_context(["list"], settings)

        assert result.exit_code == 0
        assert _JOB_UUID[:8] in result.output
        params = client.get.call_args[1]["params"]
        assert params["page"] == 1

    def test_list_json_mode(self, tmp_path) -> None:
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.get = AsyncMock(return_value=_mock_response(200, _JOB_LIST_RESPONSE))

        with patch("minitest_cli.commands.generate.ApiClient", return_value=client):
            result = _run_with_context(["list"], settings, json_mode=True)

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["items"][0]["id"] == _JOB_UUID

    def test_list_empty(self, tmp_path) -> None:
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.get = AsyncMock(
            return_value=_mock_response(200, {"items": [], "total": 0, "page": 1, "pageSize": 20})
        )

        with patch("minitest_cli.commands.generate.ApiClient", return_value=client):
            result = _run_with_context(["list"], settings)

        assert result.exit_code == 0
        assert "No generation jobs found" in result.output

    def test_list_network_error_exits_3(self, tmp_path) -> None:
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))

        with patch("minitest_cli.commands.generate.ApiClient", return_value=client):
            result = _run_with_context(["list"], settings)

        assert result.exit_code == 3
