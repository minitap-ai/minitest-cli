"""Tests for minitest_cli.commands.app_knowledge — `app-knowledge get/update`."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import typer
from typer.testing import CliRunner

from minitest_cli.commands.app_knowledge import app as app_knowledge_app
from minitest_cli.core.config import Settings

runner = CliRunner()


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
        return runner.invoke(app_knowledge_app, args)
    finally:
        for p in patches:
            p.stop()


def _mock_response(status_code=200, json_data=None):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = json.dumps(json_data) if json_data is not None else ""
    return resp


def _mock_client(method_name, resp):
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    setattr(client, method_name, AsyncMock(return_value=resp))
    return client


# ---------------------------------------------------------------------------
# `app-knowledge get`
# ---------------------------------------------------------------------------


class TestGetAppKnowledge:
    _CONFIG = {
        "id": "cfg-1",
        "appId": "app-1",
        "tenantId": "t-1",
        "appKnowledge": "# App Knowledge\n\nThis is the markdown content.",
        "createdAt": "2024-01-01T00:00:00Z",
        "updatedAt": "2024-01-02T00:00:00Z",
    }

    def test_human_prints_content(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client("get", _mock_response(200, self._CONFIG))

        with patch(
            "minitest_cli.commands.app_knowledge_helpers.ApiClient",
            return_value=client,
        ):
            result = _run_with_context(["get", "--app", "app-1"], settings)

        assert result.exit_code == 0, result.output
        assert "App Knowledge" in result.output
        client.get.assert_called_once_with("/api/v1/apps/app-1/test-config")

    def test_json_returns_record(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client("get", _mock_response(200, self._CONFIG))

        with patch(
            "minitest_cli.commands.app_knowledge_helpers.ApiClient",
            return_value=client,
        ):
            result = _run_with_context(
                ["get", "--app", "app-1"],
                settings,
                json_mode=True,
            )

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["appId"] == "app-1"
        assert "App Knowledge" in data["content"]

    def test_empty_content(self, tmp_path):
        settings = _make_settings(tmp_path)
        config = {**self._CONFIG, "appKnowledge": None}
        client = _mock_client("get", _mock_response(200, config))

        with patch(
            "minitest_cli.commands.app_knowledge_helpers.ApiClient",
            return_value=client,
        ):
            result = _run_with_context(["get", "--app", "app-1"], settings)

        assert result.exit_code == 0

    def test_missing_app_flag(self, tmp_path):
        settings = _make_settings(tmp_path)
        result = _run_with_context(["get"], settings)
        assert result.exit_code != 0

    def test_auth_required(self, tmp_path):
        settings = _make_settings(tmp_path, token=None)
        result = _run_with_context(["get", "--app", "app-1"], settings)
        assert result.exit_code == 2

    def test_app_not_found(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client("get", _mock_response(404, {"detail": "App not found"}))

        with patch(
            "minitest_cli.commands.app_knowledge_helpers.ApiClient",
            return_value=client,
        ):
            result = _run_with_context(["get", "--app", "nope"], settings)

        assert result.exit_code == 4

    def test_network_error(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.get = AsyncMock(side_effect=httpx.ConnectError("boom"))

        with patch(
            "minitest_cli.commands.app_knowledge_helpers.ApiClient",
            return_value=client,
        ):
            result = _run_with_context(["get", "--app", "app-1"], settings)

        assert result.exit_code == 3


# ---------------------------------------------------------------------------
# `app-knowledge update`
# ---------------------------------------------------------------------------


class TestUpdateAppKnowledge:
    _RESPONSE = {
        "appId": "app-1",
        "content": "# Updated\n",
        "versionNumber": 7,
        "createdAt": "2024-01-03T00:00:00Z",
    }

    def test_inline_content_happy_path(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client("put", _mock_response(200, self._RESPONSE))

        with patch(
            "minitest_cli.commands.app_knowledge_helpers.ApiClient",
            return_value=client,
        ):
            result = _run_with_context(
                ["update", "--app", "app-1", "--content", "# Updated"],
                settings,
            )

        assert result.exit_code == 0, result.output
        assert "7" in result.output
        client.put.assert_called_once()
        args, kwargs = client.put.call_args
        assert args[0] == "/api/v1/apps/app-1/app-knowledge"
        assert kwargs["json"] == {"content": "# Updated"}

    def test_content_file_happy_path(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client("put", _mock_response(200, self._RESPONSE))
        knowledge = tmp_path / "knowledge.md"
        knowledge.write_text("# From file\n")

        with patch(
            "minitest_cli.commands.app_knowledge_helpers.ApiClient",
            return_value=client,
        ):
            result = _run_with_context(
                ["update", "--app", "app-1", "--content-file", str(knowledge)],
                settings,
            )

        assert result.exit_code == 0, result.output
        _, kwargs = client.put.call_args
        assert kwargs["json"] == {"content": "# From file\n"}

    def test_json_mode_returns_full_record(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client("put", _mock_response(200, self._RESPONSE))

        with patch(
            "minitest_cli.commands.app_knowledge_helpers.ApiClient",
            return_value=client,
        ):
            result = _run_with_context(
                ["update", "--app", "app-1", "--content", "# x"],
                settings,
                json_mode=True,
            )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["versionNumber"] == 7

    def test_neither_content_nor_file_errors(self, tmp_path):
        settings = _make_settings(tmp_path)
        result = _run_with_context(["update", "--app", "app-1"], settings)
        assert result.exit_code == 1

    def test_both_content_and_file_errors(self, tmp_path):
        settings = _make_settings(tmp_path)
        knowledge = tmp_path / "knowledge.md"
        knowledge.write_text("# x")
        result = _run_with_context(
            [
                "update",
                "--app",
                "app-1",
                "--content",
                "# y",
                "--content-file",
                str(knowledge),
            ],
            settings,
        )
        assert result.exit_code == 1

    def test_empty_inline_content_errors(self, tmp_path):
        settings = _make_settings(tmp_path)
        result = _run_with_context(["update", "--app", "app-1", "--content", ""], settings)
        assert result.exit_code == 1

    def test_empty_file_errors(self, tmp_path):
        settings = _make_settings(tmp_path)
        knowledge = tmp_path / "empty.md"
        knowledge.write_text("")
        result = _run_with_context(
            ["update", "--app", "app-1", "--content-file", str(knowledge)],
            settings,
        )
        assert result.exit_code == 1

    def test_missing_app_flag(self, tmp_path):
        settings = _make_settings(tmp_path)
        result = _run_with_context(["update", "--content", "x"], settings)
        assert result.exit_code != 0

    def test_auth_required(self, tmp_path):
        settings = _make_settings(tmp_path, token=None)
        result = _run_with_context(["update", "--app", "app-1", "--content", "x"], settings)
        assert result.exit_code == 2

    def test_validation_error(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client("put", _mock_response(400, {"detail": "content required"}))
        with patch(
            "minitest_cli.commands.app_knowledge_helpers.ApiClient",
            return_value=client,
        ):
            result = _run_with_context(["update", "--app", "app-1", "--content", "x"], settings)
        assert result.exit_code == 1

    def test_app_not_found(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client("put", _mock_response(404, {"detail": "app not found"}))
        with patch(
            "minitest_cli.commands.app_knowledge_helpers.ApiClient",
            return_value=client,
        ):
            result = _run_with_context(["update", "--app", "nope", "--content", "x"], settings)
        assert result.exit_code == 4

    def test_backend_5xx(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client("put", _mock_response(503, {"detail": "service unavailable"}))
        with patch(
            "minitest_cli.commands.app_knowledge_helpers.ApiClient",
            return_value=client,
        ):
            result = _run_with_context(["update", "--app", "app-1", "--content", "x"], settings)
        assert result.exit_code == 3

    def test_response_missing_version_number(self, tmp_path):
        settings = _make_settings(tmp_path)
        # No versionNumber in payload; human mode should fail clearly.
        client = _mock_client("put", _mock_response(200, {"appId": "app-1", "content": "x"}))
        with patch(
            "minitest_cli.commands.app_knowledge_helpers.ApiClient",
            return_value=client,
        ):
            result = _run_with_context(["update", "--app", "app-1", "--content", "x"], settings)
        assert result.exit_code == 1
