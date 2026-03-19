"""Tests for minitest_cli.commands.build — CLI commands upload, list."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import typer
from click.exceptions import Exit
from typer.testing import CliRunner

from minitest_cli.commands.build import app as build_app
from minitest_cli.commands.build_helpers import (
    detect_platform,
    format_build_row,
    format_file_size,
    format_pagination_info,
    handle_response_error,
)
from minitest_cli.core.config import Settings
from minitest_cli.models import BuildListResponse, BuildResponse

runner = CliRunner()


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
        return runner.invoke(build_app, args)
    finally:
        for p in patches:
            p.stop()


def _mock_response(status_code: int = 200, json_data: object = None) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = json.dumps(json_data) if json_data else ""
    return resp


# ---------------------------------------------------------------------------
# Helper unit tests
# ---------------------------------------------------------------------------


class TestDetectPlatform:
    def test_apk_returns_android(self, tmp_path: Path) -> None:
        f = tmp_path / "build.apk"
        f.touch()
        assert detect_platform(f) == "android"

    def test_ipa_returns_ios(self, tmp_path: Path) -> None:
        f = tmp_path / "build.ipa"
        f.touch()
        assert detect_platform(f) == "ios"

    def test_unknown_extension_exits(self, tmp_path: Path) -> None:
        f = tmp_path / "build.zip"
        f.touch()
        with pytest.raises(Exit):
            detect_platform(f)


class TestFormatFileSize:
    def test_none_returns_dash(self) -> None:
        assert format_file_size(None) == "—"


class TestFormatBuildRow:
    def test_formats_complete_build(self) -> None:
        build = BuildResponse.model_validate(
            {
                "id": "b1",
                "appId": "app-1",
                "platform": "android",
                "storagePath": "/builds/b1.apk",
                "originalName": "app.apk",
                "sizeBytes": 1024,
                "createdAt": "2025-01-01T00:00:00Z",
            }
        )
        row = format_build_row(build)
        assert row[0] == "b1"
        assert row[1] == "android"
        assert row[2] == "app.apk"
        assert row[3] == "1.0 KB"
        assert "2025-01-01" in row[4]


class TestHandleResponseError:
    def test_404_exits_4(self) -> None:
        resp = _mock_response(404, {"detail": "not found"})
        with pytest.raises(Exit) as exc_info:
            handle_response_error(resp)
        assert exc_info.value.exit_code == 4

    def test_500_exits_3(self) -> None:
        resp = _mock_response(500, {"detail": "server error"})
        with pytest.raises(Exit) as exc_info:
            handle_response_error(resp)
        assert exc_info.value.exit_code == 3


class TestFormatPaginationInfo:
    def test_with_total_shows_page_and_range(self) -> None:
        data = BuildListResponse(items=[], total=50, page=1, page_size=20)
        title, tip = format_pagination_info(data)
        assert "page 1 of 3" in title
        assert "1–20 of 50" in title
        assert "--page 2" in tip

    def test_last_page_no_next_tip(self) -> None:
        data = BuildListResponse(items=[], total=15, page=1, page_size=20)
        title, tip = format_pagination_info(data)
        assert "page 1 of 1" in title
        assert tip == ""


# ---------------------------------------------------------------------------
# Upload command
# ---------------------------------------------------------------------------

_UPLOAD_RESPONSE = {
    "id": "b1",
    "appId": "app-123",
    "platform": "android",
    "storagePath": "/builds/b1.apk",
    "originalName": "app.apk",
    "sizeBytes": 5242880,
    "createdAt": "2025-01-15T12:00:00Z",
}

_LIST_DATA = {
    "items": [
        {
            "id": "b1",
            "appId": "app-123",
            "platform": "android",
            "storagePath": "/builds/b1.apk",
            "originalName": "app.apk",
            "sizeBytes": 5242880,
            "createdAt": "2025-01-15T12:00:00Z",
        },
        {
            "id": "b2",
            "appId": "app-123",
            "platform": "ios",
            "storagePath": "/builds/b2.app",
            "originalName": "app.app",
            "sizeBytes": 10485760,
            "createdAt": "2025-01-14T12:00:00Z",
        },
    ],
    "total": 2,
    "page": 1,
    "pageSize": 20,
}


def _mock_upload_client(resp: MagicMock) -> AsyncMock:
    client = AsyncMock()
    client.upload_file = AsyncMock(return_value=resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


def _mock_list_client(resp: MagicMock) -> AsyncMock:
    client = AsyncMock()
    client.get = AsyncMock(return_value=resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


class TestUploadCommand:
    def test_upload_auto_detects_platform_and_posts_to_correct_endpoint(
        self, tmp_path: Path
    ) -> None:
        build_file = tmp_path / "app.apk"
        build_file.write_bytes(b"fake-apk")
        settings = _make_settings(tmp_path)
        client = _mock_upload_client(_mock_response(200, _UPLOAD_RESPONSE))

        with patch("minitest_cli.commands.build.ApiClient", return_value=client):
            result = _run_with_context(["upload", str(build_file)], settings, json_mode=True)

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["platform"] == "android"
        call_args = client.upload_file.call_args
        assert call_args[0][0] == "/api/v1/apps/app-123/build"
        assert call_args[1]["data"] == {"platform": "android"}

    def test_upload_explicit_platform_overrides_detection(self, tmp_path: Path) -> None:
        build_file = tmp_path / "build.zip"
        build_file.write_bytes(b"data")
        settings = _make_settings(tmp_path)
        client = _mock_upload_client(_mock_response(200, _UPLOAD_RESPONSE))

        with patch("minitest_cli.commands.build.ApiClient", return_value=client):
            result = _run_with_context(
                ["upload", str(build_file), "--platform", "android"],
                settings,
                json_mode=True,
            )

        assert result.exit_code == 0
        assert client.upload_file.call_args[1]["data"] == {"platform": "android"}

    def test_upload_unknown_extension_no_platform_exits_1(self, tmp_path: Path) -> None:
        build_file = tmp_path / "build.zip"
        build_file.write_bytes(b"data")
        settings = _make_settings(tmp_path)
        result = _run_with_context(["upload", str(build_file)], settings)
        assert result.exit_code == 1

    def test_upload_network_error_exits_3(self, tmp_path: Path) -> None:
        build_file = tmp_path / "net.apk"
        build_file.write_bytes(b"data")
        settings = _make_settings(tmp_path)
        client = AsyncMock()
        client.upload_file = AsyncMock(side_effect=httpx.ConnectError("refused"))
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        with patch("minitest_cli.commands.build.ApiClient", return_value=client):
            result = _run_with_context(["upload", str(build_file)], settings)

        assert result.exit_code == 3

    def test_upload_timeout_exits_3(self, tmp_path: Path) -> None:
        build_file = tmp_path / "big.apk"
        build_file.write_bytes(b"data")
        settings = _make_settings(tmp_path)
        client = AsyncMock()
        client.upload_file = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        with patch("minitest_cli.commands.build.ApiClient", return_value=client):
            result = _run_with_context(["upload", str(build_file)], settings)

        assert result.exit_code == 3

    def test_upload_http_500_exits_3(self, tmp_path: Path) -> None:
        build_file = tmp_path / "fail.apk"
        build_file.write_bytes(b"data")
        settings = _make_settings(tmp_path)
        client = _mock_upload_client(_mock_response(500, {"detail": "server error"}))

        with patch("minitest_cli.commands.build.ApiClient", return_value=client):
            result = _run_with_context(["upload", str(build_file)], settings)

        assert result.exit_code == 3

    def test_upload_requires_auth(self, tmp_path: Path) -> None:
        build_file = tmp_path / "test.apk"
        build_file.write_bytes(b"data")
        settings = _make_settings(tmp_path, token=None)

        with patch(
            "minitest_cli.core.auth.require_auth",
            side_effect=typer.Exit(code=2),
        ):
            result = _run_with_context(["upload", str(build_file)], settings)

        assert result.exit_code == 2


# ---------------------------------------------------------------------------
# List command
# ---------------------------------------------------------------------------


class TestListBuildsCommand:
    def test_list_hits_correct_endpoint_and_returns_data(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        client = _mock_list_client(_mock_response(200, _LIST_DATA))

        with patch("minitest_cli.commands.build.ApiClient", return_value=client):
            result = _run_with_context(["list"], settings, json_mode=True)

        assert result.exit_code == 0
        assert client.get.call_args[0][0] == "/api/v1/apps/app-123/builds"
        data = json.loads(result.output)
        assert len(data["items"]) == 2

    def test_list_platform_filter_sent_as_param(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        client = _mock_list_client(_mock_response(200, _LIST_DATA))

        with patch("minitest_cli.commands.build.ApiClient", return_value=client):
            result = _run_with_context(["list", "--platform", "ios"], settings, json_mode=True)

        assert result.exit_code == 0
        assert client.get.call_args[1]["params"]["platform"] == "ios"

    def test_list_pagination_params_forwarded(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        client = _mock_list_client(_mock_response(200, _LIST_DATA))

        with patch("minitest_cli.commands.build.ApiClient", return_value=client):
            result = _run_with_context(
                ["list", "--page", "2", "--page-size", "10"],
                settings,
                json_mode=True,
            )

        assert result.exit_code == 0
        params = client.get.call_args[1]["params"]
        assert params["page"] == 2
        assert params["page_size"] == 10

    def test_list_network_error_exits_3(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        client = AsyncMock()
        client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        with patch("minitest_cli.commands.build.ApiClient", return_value=client):
            result = _run_with_context(["list"], settings)

        assert result.exit_code == 3

    def test_list_404_exits_4(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        client = _mock_list_client(_mock_response(404, {"detail": "app not found"}))

        with patch("minitest_cli.commands.build.ApiClient", return_value=client):
            result = _run_with_context(["list"], settings)

        assert result.exit_code == 4

    def test_list_human_mode_renders_build_data(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        client = _mock_list_client(_mock_response(200, _LIST_DATA))

        with patch("minitest_cli.commands.build.ApiClient", return_value=client):
            result = _run_with_context(["list"], settings, json_mode=False)

        assert result.exit_code == 0
        assert "b1" in result.output
        assert "b2" in result.output

    def test_list_requires_auth(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path, token=None)

        with patch(
            "minitest_cli.core.auth.require_auth",
            side_effect=typer.Exit(code=2),
        ):
            result = _run_with_context(["list"], settings)

        assert result.exit_code == 2

    def test_list_uses_app_flag_over_settings(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path, app_id=None)
        client = _mock_list_client(_mock_response(200, _LIST_DATA))

        with patch("minitest_cli.commands.build.ApiClient", return_value=client):
            result = _run_with_context(["list"], settings, json_mode=True, app_flag="flag-app-456")

        assert result.exit_code == 0
        assert client.get.call_args[0][0] == "/api/v1/apps/flag-app-456/builds"

    def test_list_all_flag_overrides_pagination(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        client = _mock_list_client(_mock_response(200, _LIST_DATA))

        with patch("minitest_cli.commands.build.ApiClient", return_value=client):
            result = _run_with_context(["list", "--all"], settings, json_mode=True)

        assert result.exit_code == 0
        params = client.get.call_args[1]["params"]
        assert params["page"] == 1
        assert params["page_size"] == 100
