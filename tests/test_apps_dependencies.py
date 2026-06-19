"""Tests for the 'apps dependencies' CLI command."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import typer
from typer.testing import CliRunner

from minitest_cli.commands.apps import app as apps_app
from minitest_cli.core.config import Settings

runner = CliRunner()

_GRAPH = {
    "nodes": [
        {"id": "s1", "name": "Login", "type": "feature"},
        {"id": "s2", "name": "Dashboard", "type": "feature"},
    ],
    "edges": [{"source": "s1", "target": "s2"}],
}


def _make_settings(tmp_path):
    return Settings(
        config_dir=tmp_path,
        token="test-token",
        supabase_url="https://test.supabase.co",
        supabase_publishable_key="test-key",
    )


def _patch_context(settings, json_mode=False):
    return [
        patch.object(typer.Context, "settings", settings, create=True),
        patch.object(typer.Context, "json_mode", json_mode, create=True),
        patch.object(typer.Context, "app_flag", None, create=True),
    ]


def _run(args, settings, json_mode=False):
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


class TestDependencies:
    def test_mermaid_output(self, tmp_path):
        settings = _make_settings(tmp_path)
        resp = _mock_response(200, _GRAPH)
        client = _mock_client(resp)
        with patch("minitest_cli.commands.apps_dependencies.ApiClient", return_value=client):
            result = _run(["dependencies", "app-123"], settings)
        assert result.exit_code == 0
        assert "flowchart TD" in result.output
        assert "s1 --> s2" in result.output

    def test_json_output(self, tmp_path):
        settings = _make_settings(tmp_path)
        resp = _mock_response(200, _GRAPH)
        client = _mock_client(resp)
        with patch("minitest_cli.commands.apps_dependencies.ApiClient", return_value=client):
            result = _run(["dependencies", "app-123"], settings, json_mode=True)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["nodes"][0]["id"] == "s1"
        assert data["edges"][0]["source"] == "s1"

    def test_empty_app_shows_info(self, tmp_path):
        settings = _make_settings(tmp_path)
        resp = _mock_response(200, {"nodes": [], "edges": []})
        client = _mock_client(resp)
        with patch("minitest_cli.commands.apps_dependencies.ApiClient", return_value=client):
            result = _run(["dependencies", "app-123"], settings)
        assert result.exit_code == 0

    def test_api_error_exits_3(self, tmp_path):
        settings = _make_settings(tmp_path)
        resp = _mock_response(500, {"detail": "boom"})
        client = _mock_client(resp)
        with patch("minitest_cli.commands.apps_dependencies.ApiClient", return_value=client):
            result = _run(["dependencies", "app-123"], settings)
        assert result.exit_code == 3
