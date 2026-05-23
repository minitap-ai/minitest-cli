"""Tests for minitest_cli.commands.test_profile."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import typer
from typer.testing import CliRunner

from minitest_cli.commands.test_profile import app as profile_app
from minitest_cli.core.config import Settings

runner = CliRunner()

_PROFILE = {
    "id": "p-111",
    "name": "Customer A",
    "username": "alice",
    "isShared": False,
    "updatedAt": "2026-05-22T10:00:00Z",
}

_SHARED = {
    "id": "sp-222",
    "name": "Shared Demo",
    "username": "demo",
    "isShared": True,
    "updatedAt": "2026-05-22T10:00:00Z",
}


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
        return runner.invoke(profile_app, args)
    finally:
        for p in patches:
            p.stop()


def _mock_response(status_code=200, json_data=None):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = json.dumps(json_data) if json_data else ""
    return resp


def _mock_client(get=None, post=None, patch_=None, delete=None):
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(return_value=get)
    client.post = AsyncMock(return_value=post)
    client.patch = AsyncMock(return_value=patch_)
    client.delete = AsyncMock(return_value=delete)
    return client


class TestList:
    def test_list_json(self, tmp_path):
        settings = _make_settings(tmp_path)
        resp = _mock_response(200, {"items": [_PROFILE]})
        client = _mock_client(get=resp)
        with patch("minitest_cli.commands.test_profile_list.ApiClient", return_value=client):
            result = _run(["list"], settings, json_mode=True)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["id"] == "p-111"

    def test_list_empty(self, tmp_path):
        settings = _make_settings(tmp_path)
        resp = _mock_response(200, {"items": []})
        client = _mock_client(get=resp)
        with patch("minitest_cli.commands.test_profile_list.ApiClient", return_value=client):
            result = _run(["list"], settings)
        assert result.exit_code == 0
        assert "No test profiles" in result.output


class TestListShared:
    def test_list_shared(self, tmp_path):
        settings = _make_settings(tmp_path)
        resp = _mock_response(200, {"items": [_SHARED]})
        client = _mock_client(get=resp)
        with patch("minitest_cli.commands.test_profile_list.ApiClient", return_value=client):
            result = _run(["list-shared"], settings, json_mode=True)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["id"] == "sp-222"


class TestCreate:
    def test_create_with_password(self, tmp_path):
        settings = _make_settings(tmp_path)
        resp = _mock_response(201, _PROFILE)
        client = _mock_client(post=resp)
        with patch("minitest_cli.commands.test_profile.ApiClient", return_value=client):
            result = _run(
                ["create", "--name", "Customer A", "--username", "alice", "--password", "pw"],
                settings,
                json_mode=True,
            )
        assert result.exit_code == 0
        body = client.post.await_args.kwargs["json"]
        assert body["name"] == "Customer A"
        assert body["password"] == "pw"

    def test_password_and_stdin_mutex(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client()
        with patch("minitest_cli.commands.test_profile.ApiClient", return_value=client):
            result = _run(
                ["create", "--name", "X", "--password", "pw", "--password-stdin"],
                settings,
            )
        assert result.exit_code == 1


class TestUpdate:
    def test_update_clear_password(self, tmp_path):
        settings = _make_settings(tmp_path)
        resp = _mock_response(200, _PROFILE)
        client = _mock_client(patch_=resp)
        with patch("minitest_cli.commands.test_profile.ApiClient", return_value=client):
            result = _run(
                ["update", "p-111", "--clear-password"],
                settings,
                json_mode=True,
            )
        assert result.exit_code == 0
        body = client.patch.await_args.kwargs["json"]
        assert body == {"password": None}

    def test_update_clear_and_password_rejected(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client()
        with patch("minitest_cli.commands.test_profile.ApiClient", return_value=client):
            result = _run(
                ["update", "p-111", "--password", "x", "--clear-password"],
                settings,
            )
        assert result.exit_code == 1


class TestDelete:
    def test_delete_requires_force(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client()
        with patch("minitest_cli.commands.test_profile.ApiClient", return_value=client):
            result = _run(["delete", "p-111"], settings)
        assert result.exit_code == 1
        client.delete.assert_not_awaited()

    def test_delete_force_ok(self, tmp_path):
        settings = _make_settings(tmp_path)
        resp = _mock_response(204, None)
        client = _mock_client(delete=resp)
        with patch("minitest_cli.commands.test_profile.ApiClient", return_value=client):
            result = _run(["delete", "p-111", "--force"], settings)
        assert result.exit_code == 0
        client.delete.assert_awaited_once()


class TestGet:
    def test_get_not_found(self, tmp_path):
        settings = _make_settings(tmp_path)
        resp = _mock_response(404, {"detail": "not found"})
        client = _mock_client(get=resp)
        with patch("minitest_cli.commands.test_profile.ApiClient", return_value=client):
            result = _run(["get", "missing"], settings)
        assert result.exit_code == 4
