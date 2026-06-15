"""Tests for minitest_cli.commands.user_story_bindings."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import typer
from typer.testing import CliRunner

from minitest_cli.commands.user_story_bindings import app as bindings_app
from minitest_cli.core.config import Settings

runner = CliRunner()

_FILE_ENTRY = {"id": "f-1", "name": "logo", "kind": "image"}


def _make_settings(tmp_path):
    return Settings(
        config_dir=tmp_path,
        token="t",
        supabase_url="https://x.supabase.co",
        supabase_publishable_key="k",
        app_id="app-1",
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
        return runner.invoke(bindings_app, args)
    finally:
        for p in patches:
            p.stop()


def _mock_response(status_code=200, json_data=None):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = json.dumps(json_data) if json_data else ""
    return resp


def _mock_client(get=None, put=None, patch_=None):
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(return_value=get)
    client.put = AsyncMock(return_value=put)
    client.patch = AsyncMock(return_value=patch_)
    return client


class TestSetProfile:
    def test_set_profile_ok(self, tmp_path):
        settings = _make_settings(tmp_path)
        resp = _mock_response(200, {"id": "s-1", "testProfileIds": ["p-1"]})
        client = _mock_client(patch_=resp)
        with patch("minitest_cli.commands.user_story_bindings.ApiClient", return_value=client):
            result = _run(["set-profile", "s-1", "--profile", "p-1"], settings, json_mode=True)
        assert result.exit_code == 0
        body = client.patch.await_args.kwargs["json"]
        assert body == {"testProfileIds": ["p-1"]}

    def test_set_profile_multiple(self, tmp_path):
        settings = _make_settings(tmp_path)
        resp = _mock_response(200, {"id": "s-1", "testProfileIds": ["p-1", "p-2"]})
        client = _mock_client(patch_=resp)
        with patch("minitest_cli.commands.user_story_bindings.ApiClient", return_value=client):
            result = _run(
                ["set-profile", "s-1", "--profile", "p-1", "--profile", "p-2"],
                settings,
                json_mode=True,
            )
        assert result.exit_code == 0
        body = client.patch.await_args.kwargs["json"]
        assert body == {"testProfileIds": ["p-1", "p-2"]}

    def test_set_profile_clear(self, tmp_path):
        settings = _make_settings(tmp_path)
        resp = _mock_response(200, {"id": "s-1", "testProfileIds": []})
        client = _mock_client(patch_=resp)
        with patch("minitest_cli.commands.user_story_bindings.ApiClient", return_value=client):
            result = _run(["set-profile", "s-1", "--clear"], settings, json_mode=True)
        assert result.exit_code == 0
        body = client.patch.await_args.kwargs["json"]
        assert body == {"testProfileIds": []}

    def test_set_profile_mutex(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client()
        with patch("minitest_cli.commands.user_story_bindings.ApiClient", return_value=client):
            result = _run(
                ["set-profile", "s-1", "--profile", "p-1", "--clear"],
                settings,
            )
        assert result.exit_code == 1
        client.patch.assert_not_awaited()

    def test_set_profile_requires_arg(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client()
        with patch("minitest_cli.commands.user_story_bindings.ApiClient", return_value=client):
            result = _run(["set-profile", "s-1"], settings)
        assert result.exit_code == 1


class TestSetFiles:
    def test_set_files_atomic(self, tmp_path):
        settings = _make_settings(tmp_path)
        resp = _mock_response(200, {"items": [_FILE_ENTRY], "total": 1, "page": 1, "pageSize": 50})
        client = _mock_client(put=resp)
        with patch("minitest_cli.commands.user_story_bindings.ApiClient", return_value=client):
            result = _run(
                ["set-files", "s-1", "--file", "f-1", "--file", "f-2"],
                settings,
                json_mode=True,
            )
        assert result.exit_code == 0
        body = client.put.await_args.kwargs["json"]
        assert body == {"fileIds": ["f-1", "f-2"]}

    def test_set_files_clear(self, tmp_path):
        settings = _make_settings(tmp_path)
        resp = _mock_response(200, {"items": [], "total": 0, "page": 1, "pageSize": 50})
        client = _mock_client(put=resp)
        with patch("minitest_cli.commands.user_story_bindings.ApiClient", return_value=client):
            result = _run(["set-files", "s-1", "--clear"], settings, json_mode=True)
        assert result.exit_code == 0
        body = client.put.await_args.kwargs["json"]
        assert body == {"fileIds": []}


class TestListFiles:
    def test_list_files_json(self, tmp_path):
        settings = _make_settings(tmp_path)
        resp = _mock_response(200, {"items": [_FILE_ENTRY], "total": 1, "page": 1, "pageSize": 50})
        client = _mock_client(get=resp)
        with patch("minitest_cli.commands.user_story_bindings.ApiClient", return_value=client):
            result = _run(["list-files", "s-1"], settings, json_mode=True)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["items"][0]["id"] == "f-1"
