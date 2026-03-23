"""Tests for minitest_cli.commands.apps — CLI command list."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import typer
from typer.testing import CliRunner

from minitest_cli.commands.apps import app as apps_app
from minitest_cli.core.config import Settings

runner = CliRunner()

_APPS_DATA = {
    "apps": [
        {"id": "aaa-111", "name": "My App", "tenantId": "t-1"},
        {"id": "bbb-222", "name": "Other App", "tenantId": "t-1"},
    ]
}


def _make_settings(tmp_path, **overrides):
    defaults = {
        "config_dir": tmp_path,
        "token": "test-token",
        "supabase_url": "https://test.supabase.co",
        "supabase_publishable_key": "test-key",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _patch_context(settings, json_mode=False):
    return [
        patch.object(typer.Context, "settings", settings, create=True),
        patch.object(typer.Context, "json_mode", json_mode, create=True),
        patch.object(typer.Context, "app_flag", None, create=True),
    ]


def _run_with_context(args, settings, json_mode=False):
    patches = _patch_context(settings, json_mode)
    for p in patches:
        p.start()
    try:
        return runner.invoke(apps_app, args)
    finally:
        for p in patches:
            p.stop()


def _mock_response(status_code=200, json_data=None):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = json.dumps(json_data) if json_data else ""
    return resp


def _mock_client(resp):
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(return_value=resp)
    return client


class TestListApps:
    def test_json_output(self, tmp_path):
        settings = _make_settings(tmp_path)
        resp = _mock_response(200, _APPS_DATA)
        client = _mock_client(resp)

        with patch("minitest_cli.commands.apps.ApiClient", return_value=client):
            result = _run_with_context(["list"], settings, json_mode=True)

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 2
        assert data[0]["id"] == "aaa-111"
        assert data[0]["name"] == "My App"
        assert data[1]["id"] == "bbb-222"

    def test_human_output(self, tmp_path):
        settings = _make_settings(tmp_path)
        resp = _mock_response(200, _APPS_DATA)
        client = _mock_client(resp)

        with patch("minitest_cli.commands.apps.ApiClient", return_value=client):
            result = _run_with_context(["list"], settings)

        assert result.exit_code == 0
        assert "My App" in result.output
        assert "Other App" in result.output
        assert "aaa-111" in result.output

    def test_empty_list(self, tmp_path):
        settings = _make_settings(tmp_path)
        resp = _mock_response(200, {"apps": []})
        client = _mock_client(resp)

        with patch("minitest_cli.commands.apps.ApiClient", return_value=client):
            result = _run_with_context(["list"], settings, json_mode=True)

        assert result.exit_code == 0
        assert json.loads(result.output) == []

    def test_api_error(self, tmp_path):
        settings = _make_settings(tmp_path)
        resp = _mock_response(500, {"detail": "Internal error"})
        client = _mock_client(resp)

        with patch("minitest_cli.commands.apps.ApiClient", return_value=client):
            result = _run_with_context(["list"], settings)

        assert result.exit_code == 3

    def test_network_error(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.get = AsyncMock(side_effect=httpx.ConnectError("connection refused"))

        with patch("minitest_cli.commands.apps.ApiClient", return_value=client):
            result = _run_with_context(["list"], settings)

        assert result.exit_code == 3

    def test_auth_required(self, tmp_path):
        settings = _make_settings(tmp_path, token=None)
        result = _run_with_context(["list"], settings)
        assert result.exit_code == 2

    def test_calls_correct_endpoint(self, tmp_path):
        settings = _make_settings(tmp_path)
        resp = _mock_response(200, _APPS_DATA)
        client = _mock_client(resp)

        with patch("minitest_cli.commands.apps.ApiClient", return_value=client):
            _run_with_context(["list"], settings)

        client.get.assert_called_once_with("/api/v1/apps")
