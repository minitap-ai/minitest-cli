"""Essential tests for flow commands - validates business logic, error handling, and CLI parsing."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import typer
from typer.testing import CliRunner

from minitest_cli.commands.flow import app as flow_app
from minitest_cli.core.config import Settings

runner = CliRunner()


def _make_settings(tmp_path, **overrides):
    defaults = {
        "config_dir": tmp_path,
        "token": "test-token",
        "app_id": "app-123",
        "supabase_url": "https://test.supabase.co",
        "supabase_publishable_key": "test-publishable-key",
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
        result = runner.invoke(flow_app, args)
    finally:
        for p in patches:
            p.stop()
    return result


def _mock_response(status_code=200, json_data=None):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


SAMPLE_FLOW = {
    "id": "flow-1",
    "name": "Login Flow",
    "type": "login",
    "acceptanceCriteria": [
        {"id": "ac-1", "content": "User can log in"},
        {"id": "ac-2", "content": "Error shown on bad password"},
    ],
}


class TestCreateFlow:
    def test_invalid_type_rejected(self, tmp_path):
        settings = _make_settings(tmp_path)
        result = _run_with_context(
            ["create", "--name", "Bad Flow", "--type", "invalid_type"],
            settings,
        )
        assert result.exit_code != 0

    def test_network_error_exits_3(self, tmp_path):
        settings = _make_settings(tmp_path)
        with patch("minitest_cli.commands.flow.ApiClient") as MockClient:
            instance = AsyncMock()
            instance.post.side_effect = httpx.ConnectError("Connection refused")
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            result = _run_with_context(
                ["create", "--name", "Flow", "--type", "login"],
                settings,
            )
        assert result.exit_code == 3


class TestListFlows:
    def test_invalid_type_rejected(self, tmp_path):
        settings = _make_settings(tmp_path)
        result = _run_with_context(["list", "--type", "bad_type"], settings)
        assert result.exit_code != 0

    def test_all_flag_fetches_multiple_pages(self, tmp_path):
        settings = _make_settings(tmp_path)
        page1_resp = _mock_response(
            200, {"items": [SAMPLE_FLOW], "total": 2, "page": 1, "pageSize": 100}
        )
        page2_resp = _mock_response(
            200, {"items": [SAMPLE_FLOW], "total": 2, "page": 2, "pageSize": 100}
        )
        with patch("minitest_cli.commands.flow.ApiClient") as MockClient:
            instance = AsyncMock()
            instance.get.side_effect = [page1_resp, page2_resp]
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            result = _run_with_context(["list", "--all"], settings, json_mode=True)
        assert result.exit_code == 0
        assert instance.get.call_count == 2
        data = json.loads(result.output)
        assert len(data) == 2


class TestGetFlow:
    def test_not_found_exits_4(self, tmp_path):
        settings = _make_settings(tmp_path)
        mock_resp = _mock_response(404, {"detail": "Flow not found"})
        with patch("minitest_cli.commands.flow.ApiClient") as MockClient:
            instance = AsyncMock()
            instance.get.return_value = mock_resp
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            result = _run_with_context(["get", "flow-1"], settings)
        assert result.exit_code == 4


class TestUpdateFlow:
    def test_add_criteria_fetches_and_appends(self, tmp_path):
        settings = _make_settings(tmp_path)
        get_resp = _mock_response(200, SAMPLE_FLOW)
        patch_resp = _mock_response(200, SAMPLE_FLOW)
        with patch("minitest_cli.commands.flow_modify.ApiClient") as MockClient:
            instance = AsyncMock()
            instance.get.return_value = get_resp
            instance.patch.return_value = patch_resp
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            result = _run_with_context(
                ["update", "flow-1", "--add-criteria", "New criterion"],
                settings,
                json_mode=True,
            )
        assert result.exit_code == 0
        instance.get.assert_called_once()
        call_kwargs = instance.patch.call_args
        criteria = call_kwargs.kwargs["json"]["acceptance_criteria"]
        assert "User can log in" in criteria
        assert "Error shown on bad password" in criteria
        assert "New criterion" in criteria

    def test_empty_payload_rejected(self, tmp_path):
        settings = _make_settings(tmp_path)
        result = _run_with_context(["update", "flow-1"], settings)
        assert result.exit_code == 1
        assert "Provide at least one field to update" in result.output

    def test_conflicting_criteria_flags_rejected(self, tmp_path):
        settings = _make_settings(tmp_path)
        result = _run_with_context(
            ["update", "flow-1", "--criteria", "A", "--add-criteria", "B"],
            settings,
        )
        assert result.exit_code == 1
        assert "Use either --criteria or --add-criteria, not both" in result.output


class TestDeleteFlow:
    def test_requires_force_flag(self, tmp_path):
        settings = _make_settings(tmp_path)
        result = _run_with_context(["delete", "flow-1"], settings)
        assert result.exit_code == 1

    def test_not_found_exits_4(self, tmp_path):
        settings = _make_settings(tmp_path)
        mock_resp = _mock_response(404, {"detail": "Flow not found"})
        with patch("minitest_cli.commands.flow_modify.ApiClient") as MockClient:
            instance = AsyncMock()
            instance.delete.return_value = mock_resp
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            result = _run_with_context(["delete", "flow-1", "--force"], settings)
        assert result.exit_code == 4
