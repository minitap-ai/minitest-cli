"""Tests for minitest_cli.commands.test_file."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import typer
from typer.testing import CliRunner

from minitest_cli.commands.test_file import app as file_app
from minitest_cli.core.config import Settings

runner = CliRunner()

_FILE = {
    "id": "f-1",
    "name": "logo",
    "originalFilename": "logo.png",
    "kind": "image",
    "mimeType": "image/png",
    "sizeBytes": 1024,
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
        return runner.invoke(file_app, args)
    finally:
        for p in patches:
            p.stop()


def _mock_response(status_code=200, json_data=None):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = json.dumps(json_data) if json_data else ""
    return resp


def _mock_client(get=None, upload=None, patch_=None, delete=None):
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(return_value=get)
    client.upload_file = AsyncMock(return_value=upload)
    client.patch = AsyncMock(return_value=patch_)
    client.delete = AsyncMock(return_value=delete)
    return client


class TestList:
    def test_list_json(self, tmp_path):
        settings = _make_settings(tmp_path)
        resp = _mock_response(200, {"items": [_FILE]})
        client = _mock_client(get=resp)
        with patch("minitest_cli.commands.test_file_list.ApiClient", return_value=client):
            result = _run(["list"], settings, json_mode=True)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["id"] == "f-1"


class TestUpload:
    def test_upload_too_large(self, tmp_path):
        settings = _make_settings(tmp_path)
        big = tmp_path / "huge.bin"
        big.write_bytes(b"x" * (26 * 1024 * 1024))
        client = _mock_client()
        with patch("minitest_cli.commands.test_file.ApiClient", return_value=client):
            result = _run(["upload", str(big)], settings)
        assert result.exit_code == 1
        client.upload_file.assert_not_awaited()

    def test_upload_ok(self, tmp_path):
        settings = _make_settings(tmp_path)
        local = tmp_path / "logo.png"
        local.write_bytes(b"PNGDATA")
        resp = _mock_response(201, _FILE)
        client = _mock_client(upload=resp)
        with patch("minitest_cli.commands.test_file.ApiClient", return_value=client):
            result = _run(["upload", str(local), "--note", "logo"], settings, json_mode=True)
        assert result.exit_code == 0
        assert client.upload_file.await_args.kwargs["data"]["note"] == "logo"


class TestUpdate:
    def test_clear_and_note_rejected(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client()
        with patch("minitest_cli.commands.test_file.ApiClient", return_value=client):
            result = _run(["update", "f-1", "--note", "x", "--clear-note"], settings)
        assert result.exit_code == 1


class TestDelete:
    def test_delete_requires_force(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client()
        with patch("minitest_cli.commands.test_file.ApiClient", return_value=client):
            result = _run(["delete", "f-1"], settings)
        assert result.exit_code == 1
        client.delete.assert_not_awaited()


class TestGet:
    def test_get_not_found(self, tmp_path):
        settings = _make_settings(tmp_path)
        resp = _mock_response(404, {"detail": "not found"})
        client = _mock_client(get=resp)
        with patch("minitest_cli.commands.test_file.ApiClient", return_value=client):
            result = _run(["get", "missing"], settings)
        assert result.exit_code == 4
