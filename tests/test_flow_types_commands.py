"""Tests for minitest_cli.commands.flow_types — `flow-types list`."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import typer
from typer.testing import CliRunner

from minitest_cli.commands.flow_types import app as flow_types_app
from minitest_cli.core.config import Settings

runner = CliRunner()

_TYPES = ["login", "registration", "onboarding", "search", "settings", "other"]


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
        return runner.invoke(flow_types_app, args)
    finally:
        for p in patches:
            p.stop()


def _mock_response(status_code=200, json_data=None):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = json.dumps(json_data) if json_data is not None else ""
    return resp


def _mock_client(resp):
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(return_value=resp)
    return client


class TestListFlowTypes:
    def test_human_output_one_per_line(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client(_mock_response(200, _TYPES))

        with patch("minitest_cli.commands.flow_types.ApiClient", return_value=client):
            result = _run_with_context(["list"], settings)

        assert result.exit_code == 0, result.output
        for value in _TYPES:
            assert value in result.output
        # One per line
        lines = [line.strip() for line in result.output.splitlines() if line.strip()]
        assert lines == _TYPES

    def test_json_output(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client(_mock_response(200, _TYPES))

        with patch("minitest_cli.commands.flow_types.ApiClient", return_value=client):
            result = _run_with_context(["list"], settings, json_mode=True)

        assert result.exit_code == 0, result.output
        assert json.loads(result.output) == _TYPES

    def test_calls_correct_endpoint(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client(_mock_response(200, _TYPES))

        with patch("minitest_cli.commands.flow_types.ApiClient", return_value=client):
            _run_with_context(["list"], settings)

        client.get.assert_called_once_with("/api/v1/user-story-types")

    def test_auth_required(self, tmp_path):
        settings = _make_settings(tmp_path, token=None)
        result = _run_with_context(["list"], settings)
        assert result.exit_code == 2

    def test_api_error(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client(_mock_response(500, {"detail": "boom"}))

        with patch("minitest_cli.commands.flow_types.ApiClient", return_value=client):
            result = _run_with_context(["list"], settings)

        assert result.exit_code == 3

    def test_auth_failure_maps_to_exit_1(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client(_mock_response(401, {"detail": "expired"}))

        with patch("minitest_cli.commands.flow_types.ApiClient", return_value=client):
            result = _run_with_context(["list"], settings)

        assert result.exit_code == 1

    def test_network_error(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.get = AsyncMock(side_effect=httpx.ConnectError("boom"))

        with patch("minitest_cli.commands.flow_types.ApiClient", return_value=client):
            result = _run_with_context(["list"], settings)

        assert result.exit_code == 3

    def test_unexpected_response_shape(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client(_mock_response(200, {"not": "a list"}))

        with patch("minitest_cli.commands.flow_types.ApiClient", return_value=client):
            result = _run_with_context(["list"], settings)

        assert result.exit_code == 3

    def test_empty_list_human(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client(_mock_response(200, []))

        with patch("minitest_cli.commands.flow_types.ApiClient", return_value=client):
            result = _run_with_context(["list"], settings)

        assert result.exit_code == 0
