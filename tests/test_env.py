"""Tests for minitest_cli.commands.env — list/get/set/unset/clear."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from typer.testing import CliRunner

from minitest_cli.commands import env
from minitest_cli.core.config import Settings

runner = CliRunner()

_APP_ID = "33333333-3333-3333-3333-333333333333"
_TENANT_ID = "11111111-1111-1111-1111-111111111111"

_APPS_PAYLOAD = {
    "apps": [{"id": _APP_ID, "name": "my-app", "tenantId": _TENANT_ID, "platforms": ["ios"]}]
}


def _make_settings(tmp_path, **overrides):
    defaults = {
        "config_dir": tmp_path,
        "token": "test-token",
        "supabase_url": "https://test.supabase.co",
        "supabase_publishable_key": "test-key",
        "app_id": _APP_ID,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _mock_response(status_code=200, json_data=None):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = json.dumps(json_data) if json_data else ""
    return resp


def _mock_client(responses: dict[str, MagicMock]):
    """Async-context client whose method calls return the mapped responses."""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    for method, resp in responses.items():
        setattr(client, method, AsyncMock(return_value=resp))
    return client


def _env_response(env_vars: dict[str, str]):
    return _mock_response(
        200,
        {
            "id": "e1",
            "appId": _APP_ID,
            "tenantId": _TENANT_ID,
            "envVars": env_vars,
            "updatedAt": "2024-01-01T00:00:00Z",
        },
    )


def _invoke(args, settings, *, apps_resp, apps_manager_resp, json_mode=False):
    apps_client = _mock_client({"get": apps_resp})
    am_client = _mock_client(apps_manager_resp)
    with (
        patch.object(env, "_get_settings", return_value=settings),
        patch.object(env, "_get_app_flag", return_value=None),
        patch.object(env, "_is_json_mode", return_value=json_mode),
        patch("minitest_cli.commands.env_helpers.ApiClient", return_value=apps_client),
        patch("minitest_cli.commands.env_helpers.AppsManagerClient", return_value=am_client),
    ):
        return runner.invoke(env.app, args)


class TestList:
    def test_masks_values_by_default(self, tmp_path):
        settings = _make_settings(tmp_path)
        result = _invoke(
            ["list"],
            settings,
            apps_resp=_mock_response(200, _APPS_PAYLOAD),
            apps_manager_resp={"get": _env_response({"API_KEY": "supersecret"})},
        )
        assert result.exit_code == 0, result.output
        assert "API_KEY" in result.stdout
        assert "supersecret" not in result.stdout
        assert "********" in result.stdout

    def test_show_reveals_values(self, tmp_path):
        settings = _make_settings(tmp_path)
        result = _invoke(
            ["list", "--show"],
            settings,
            apps_resp=_mock_response(200, _APPS_PAYLOAD),
            apps_manager_resp={"get": _env_response({"API_KEY": "supersecret"})},
        )
        assert result.exit_code == 0, result.output
        assert "supersecret" in result.stdout

    def test_no_env_vars_reports_empty(self, tmp_path):
        settings = _make_settings(tmp_path)
        result = _invoke(
            ["list"],
            settings,
            apps_resp=_mock_response(200, _APPS_PAYLOAD),
            apps_manager_resp={"get": _mock_response(404, {"detail": "not found"})},
        )
        assert result.exit_code == 0, result.output
        assert "No environment variables" in result.output


class TestGet:
    def test_prints_value_verbatim(self, tmp_path):
        settings = _make_settings(tmp_path)
        result = _invoke(
            ["get", "API_KEY"],
            settings,
            apps_resp=_mock_response(200, _APPS_PAYLOAD),
            apps_manager_resp={"get": _env_response({"API_KEY": "supersecret"})},
        )
        assert result.exit_code == 0, result.output
        assert result.stdout.strip() == "supersecret"

    def test_missing_key_exits_not_found(self, tmp_path):
        settings = _make_settings(tmp_path)
        result = _invoke(
            ["get", "ABSENT"],
            settings,
            apps_resp=_mock_response(200, _APPS_PAYLOAD),
            apps_manager_resp={"get": _env_response({"API_KEY": "x"})},
        )
        assert result.exit_code == 4


class TestSet:
    def test_without_yes_refuses_and_does_not_write(self, tmp_path):
        settings = _make_settings(tmp_path)
        am_client = _mock_client({"get": _env_response({"A": "1"})})
        apps_client = _mock_client({"get": _mock_response(200, _APPS_PAYLOAD)})
        with (
            patch.object(env, "_get_settings", return_value=settings),
            patch.object(env, "_get_app_flag", return_value=None),
            patch.object(env, "_is_json_mode", return_value=False),
            patch("minitest_cli.commands.env_helpers.ApiClient", return_value=apps_client),
            patch("minitest_cli.commands.env_helpers.AppsManagerClient", return_value=am_client),
        ):
            result = runner.invoke(env.app, ["set", "B", "2"])
        assert result.exit_code == 1
        assert "--yes" in result.output
        am_client.put.assert_not_called()

    def test_yes_merges_and_puts_full_set(self, tmp_path):
        settings = _make_settings(tmp_path)
        am_client = _mock_client(
            {"get": _env_response({"A": "1"}), "put": _env_response({"A": "1", "B": "2"})}
        )
        apps_client = _mock_client({"get": _mock_response(200, _APPS_PAYLOAD)})
        with (
            patch.object(env, "_get_settings", return_value=settings),
            patch.object(env, "_get_app_flag", return_value=None),
            patch.object(env, "_is_json_mode", return_value=False),
            patch("minitest_cli.commands.env_helpers.ApiClient", return_value=apps_client),
            patch("minitest_cli.commands.env_helpers.AppsManagerClient", return_value=am_client),
        ):
            result = runner.invoke(env.app, ["set", "B", "2", "--yes"])
        assert result.exit_code == 0, result.output
        am_client.put.assert_awaited_once()
        sent = am_client.put.call_args.kwargs["json"]["envVars"]
        assert sent == {"A": "1", "B": "2"}

    def test_dry_run_shows_diff_without_writing(self, tmp_path):
        settings = _make_settings(tmp_path)
        am_client = _mock_client({"get": _env_response({"A": "1"})})
        apps_client = _mock_client({"get": _mock_response(200, _APPS_PAYLOAD)})
        with (
            patch.object(env, "_get_settings", return_value=settings),
            patch.object(env, "_get_app_flag", return_value=None),
            patch.object(env, "_is_json_mode", return_value=False),
            patch("minitest_cli.commands.env_helpers.ApiClient", return_value=apps_client),
            patch("minitest_cli.commands.env_helpers.AppsManagerClient", return_value=am_client),
        ):
            result = runner.invoke(env.app, ["set", "B", "2", "--dry-run"])
        assert result.exit_code == 0, result.output
        assert "+ B" in result.output
        am_client.put.assert_not_called()


class TestUnset:
    def test_yes_removes_key_and_keeps_others(self, tmp_path):
        settings = _make_settings(tmp_path)
        am_client = _mock_client(
            {"get": _env_response({"A": "1", "B": "2"}), "put": _env_response({"A": "1"})}
        )
        apps_client = _mock_client({"get": _mock_response(200, _APPS_PAYLOAD)})
        with (
            patch.object(env, "_get_settings", return_value=settings),
            patch.object(env, "_get_app_flag", return_value=None),
            patch.object(env, "_is_json_mode", return_value=False),
            patch("minitest_cli.commands.env_helpers.ApiClient", return_value=apps_client),
            patch("minitest_cli.commands.env_helpers.AppsManagerClient", return_value=am_client),
        ):
            result = runner.invoke(env.app, ["unset", "B", "--yes"])
        assert result.exit_code == 0, result.output
        sent = am_client.put.call_args.kwargs["json"]["envVars"]
        assert sent == {"A": "1"}

    def test_missing_key_exits_not_found(self, tmp_path):
        settings = _make_settings(tmp_path)
        result = _invoke(
            ["unset", "ABSENT", "--yes"],
            settings,
            apps_resp=_mock_response(200, _APPS_PAYLOAD),
            apps_manager_resp={"get": _env_response({"A": "1"})},
        )
        assert result.exit_code == 4


class TestClear:
    def test_yes_deletes_all(self, tmp_path):
        settings = _make_settings(tmp_path)
        am_client = _mock_client({"get": _env_response({"A": "1"}), "delete": _mock_response(204)})
        apps_client = _mock_client({"get": _mock_response(200, _APPS_PAYLOAD)})
        with (
            patch.object(env, "_get_settings", return_value=settings),
            patch.object(env, "_get_app_flag", return_value=None),
            patch.object(env, "_is_json_mode", return_value=False),
            patch("minitest_cli.commands.env_helpers.ApiClient", return_value=apps_client),
            patch("minitest_cli.commands.env_helpers.AppsManagerClient", return_value=am_client),
        ):
            result = runner.invoke(env.app, ["clear", "--yes"])
        assert result.exit_code == 0, result.output
        am_client.delete.assert_awaited_once()

    def test_without_yes_refuses(self, tmp_path):
        settings = _make_settings(tmp_path)
        am_client = _mock_client({"get": _env_response({"A": "1"})})
        apps_client = _mock_client({"get": _mock_response(200, _APPS_PAYLOAD)})
        with (
            patch.object(env, "_get_settings", return_value=settings),
            patch.object(env, "_get_app_flag", return_value=None),
            patch.object(env, "_is_json_mode", return_value=False),
            patch("minitest_cli.commands.env_helpers.ApiClient", return_value=apps_client),
            patch("minitest_cli.commands.env_helpers.AppsManagerClient", return_value=am_client),
        ):
            result = runner.invoke(env.app, ["clear"])
        assert result.exit_code == 1
        assert "--yes" in result.output
        am_client.delete.assert_not_called()
