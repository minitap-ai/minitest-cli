"""Tests for minitest_cli.commands.flow_types — `flow-types` list, create and update."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import typer
from typer.testing import CliRunner

from minitest_cli.commands.flow_types import app as flow_types_app
from minitest_cli.core.config import Settings

runner = CliRunner()

_TYPES = ["login", "registration", "onboarding", "search", "settings", "other"]

_CUSTOM_TYPE_JSON = {
    "id": "cft-1",
    "tenantId": "tenant-1",
    "name": "Payments",
    "icon": "credit-card",
    "color": "green",
    "usagePrompt": None,
    "createdAt": "2026-01-01T00:00:00Z",
}

_CUSTOM_TYPES_PATH = "/api/v1/apps/app-1/custom-user-story-types"


def _make_settings(tmp_path, **overrides):
    defaults = {
        "config_dir": tmp_path,
        "token": "test-token",
        "supabase_url": "https://test.supabase.co",
        "supabase_publishable_key": "test-key",
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


def _names(result):
    return [item["name"] for item in json.loads(result.output)]


def _apps_response(*tenant_ids):
    apps = [
        {"id": f"app-{i}", "name": f"App {i}", "tenantId": tenant_id}
        for i, tenant_id in enumerate(tenant_ids, start=1)
    ]
    return _mock_response(200, {"apps": apps})


def _mock_client(*get_responses, write_response=None):
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(side_effect=list(get_responses))
    client.post = AsyncMock(return_value=write_response)
    client.patch = AsyncMock(return_value=write_response)
    return client


class TestListFlowTypes:
    def test_human_output_one_per_line(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client(_mock_response(200, _TYPES), _mock_response(200, []))

        with patch("minitest_cli.commands.flow_types.ApiClient", return_value=client):
            result = _run_with_context(["list"], settings, app_flag="app-1")

        assert result.exit_code == 0, result.output
        lines = [line.strip() for line in result.output.splitlines() if line.strip()]
        assert lines == _TYPES

    def test_custom_types_are_appended(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client(_mock_response(200, _TYPES), _mock_response(200, [_CUSTOM_TYPE_JSON]))

        with patch("minitest_cli.commands.flow_types.ApiClient", return_value=client):
            result = _run_with_context(["list"], settings, json_mode=True, app_flag="app-1")

        assert result.exit_code == 0, result.output
        assert _names(result) == [*_TYPES, "Payments"]
        assert json.loads(result.output)[-1] == {
            "name": "Payments",
            "custom": True,
            "id": "cft-1",
            "icon": "credit-card",
            "color": "green",
            "usagePrompt": None,
        }
        assert client.get.call_args_list[1].args == (_CUSTOM_TYPES_PATH,)

    def test_custom_types_listed_without_targeting_an_app(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client(
            _mock_response(200, _TYPES),
            _apps_response("tenant-1"),
            _mock_response(200, [_CUSTOM_TYPE_JSON]),
        )

        with patch("minitest_cli.commands.flow_types.ApiClient", return_value=client):
            result = _run_with_context(["list"], settings, json_mode=True)

        assert result.exit_code == 0, result.output
        assert _names(result) == [*_TYPES, "Payments"]
        assert client.get.call_args_list[2].args == (_CUSTOM_TYPES_PATH,)

    def test_account_spanning_several_tenants_asks_for_an_app(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client(_mock_response(200, _TYPES), _apps_response("tenant-1", "tenant-2"))

        with patch("minitest_cli.commands.flow_types.ApiClient", return_value=client):
            result = _run_with_context(["list"], settings)

        assert result.exit_code == 1
        assert "--app" in result.output

    def test_unresolvable_app_points_at_the_flag(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client(_mock_response(200, _TYPES), _apps_response())

        with patch("minitest_cli.commands.flow_types.ApiClient", return_value=client):
            result = _run_with_context(["list"], settings)

        assert result.exit_code == 4
        assert "--app" in result.output and "MINITEST_APP_ID" in result.output

    def test_json_output(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client(_mock_response(200, _TYPES), _mock_response(200, []))

        with patch("minitest_cli.commands.flow_types.ApiClient", return_value=client):
            result = _run_with_context(["list"], settings, json_mode=True, app_flag="app-1")

        assert result.exit_code == 0, result.output
        assert _names(result) == _TYPES
        assert all(item["custom"] is False for item in json.loads(result.output))

    def test_calls_correct_endpoint(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client(_mock_response(200, _TYPES), _mock_response(200, []))

        with patch("minitest_cli.commands.flow_types.ApiClient", return_value=client):
            _run_with_context(["list"], settings, app_flag="app-1")

        assert client.get.call_args_list[0].args == ("/api/v1/user-story-types",)

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
        client = _mock_client()
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


class TestCreateFlowType:
    def test_posts_to_the_tenant_custom_types_endpoint(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client(write_response=_mock_response(201, _CUSTOM_TYPE_JSON))

        with patch("minitest_cli.commands.flow_types_write.ApiClient", return_value=client):
            result = _run_with_context(
                ["create", "--name", "Payments", "--icon", "credit-card", "--color", "green"],
                settings,
                json_mode=True,
                app_flag="app-1",
            )

        assert result.exit_code == 0, result.output
        assert json.loads(result.output) == _CUSTOM_TYPE_JSON
        client.post.assert_called_once_with(
            _CUSTOM_TYPES_PATH,
            json={"name": "Payments", "icon": "credit-card", "color": "green"},
        )

    def test_usage_prompt_is_sent_when_given(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client(write_response=_mock_response(201, _CUSTOM_TYPE_JSON))

        with patch("minitest_cli.commands.flow_types_write.ApiClient", return_value=client):
            result = _run_with_context(
                ["create", "--name", "Payments", "--usage-prompt", "Use the sandbox card."],
                settings,
                app_flag="app-1",
            )

        assert result.exit_code == 0, result.output
        assert client.post.call_args.kwargs["json"]["usagePrompt"] == "Use the sandbox card."

    def test_works_without_targeting_an_app(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client(
            _apps_response("tenant-1"), write_response=_mock_response(201, _CUSTOM_TYPE_JSON)
        )

        with patch("minitest_cli.commands.flow_types_write.ApiClient", return_value=client):
            result = _run_with_context(["create", "--name", "Payments"], settings)

        assert result.exit_code == 0, result.output
        assert client.post.call_args.args == (_CUSTOM_TYPES_PATH,)

    def test_duplicate_name_surfaces_the_server_message(self, tmp_path):
        settings = _make_settings(tmp_path)
        conflict = _mock_response(
            409, {"detail": "A custom user story type with this name exists."}
        )
        client = _mock_client(write_response=conflict)

        with patch("minitest_cli.commands.flow_types_write.ApiClient", return_value=client):
            result = _run_with_context(["create", "--name", "Payments"], settings, app_flag="app-1")

        assert result.exit_code == 3
        assert "name exists" in result.output


class TestUpdateFlowType:
    def test_renames_a_type_looked_up_by_name(self, tmp_path):
        settings = _make_settings(tmp_path)
        renamed = {**_CUSTOM_TYPE_JSON, "name": "Billing"}
        client = _mock_client(
            _mock_response(200, [_CUSTOM_TYPE_JSON]), write_response=_mock_response(200, renamed)
        )

        with patch("minitest_cli.commands.flow_types_write.ApiClient", return_value=client):
            result = _run_with_context(
                ["update", "payments", "--name", "Billing"],
                settings,
                json_mode=True,
                app_flag="app-1",
            )

        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["name"] == "Billing"
        client.patch.assert_called_once_with(
            f"{_CUSTOM_TYPES_PATH}/cft-1", json={"name": "Billing"}
        )

    def test_accepts_an_id_without_listing_types(self, tmp_path):
        settings = _make_settings(tmp_path)
        type_id = "3fa85f64-5717-4562-b3fc-2c963f66afa6"
        client = _mock_client(write_response=_mock_response(200, _CUSTOM_TYPE_JSON))

        with patch("minitest_cli.commands.flow_types_write.ApiClient", return_value=client):
            result = _run_with_context(
                ["update", type_id, "--color", "blue"], settings, app_flag="app-1"
            )

        assert result.exit_code == 0, result.output
        client.get.assert_not_called()
        client.patch.assert_called_once_with(
            f"{_CUSTOM_TYPES_PATH}/{type_id}", json={"color": "blue"}
        )

    def test_unknown_name_exits_4_and_lists_existing_types(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client(_mock_response(200, [_CUSTOM_TYPE_JSON]))

        with patch("minitest_cli.commands.flow_types_write.ApiClient", return_value=client):
            result = _run_with_context(
                ["update", "nope", "--name", "Billing"], settings, app_flag="app-1"
            )

        assert result.exit_code == 4
        assert "Payments" in result.output

    def test_requires_at_least_one_field(self, tmp_path):
        settings = _make_settings(tmp_path)
        result = _run_with_context(["update", "Payments"], settings, app_flag="app-1")
        assert result.exit_code == 1
        assert "at least one field" in result.output


class TestDeleteFlowType:
    def test_deletes_a_type_looked_up_by_name(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client(_mock_response(200, [_CUSTOM_TYPE_JSON]))
        client.delete = AsyncMock(return_value=_mock_response(204, None))

        with patch("minitest_cli.commands.flow_types_write.ApiClient", return_value=client):
            result = _run_with_context(
                ["delete", "payments", "--yes"], settings, json_mode=True, app_flag="app-1"
            )

        assert result.exit_code == 0, result.output
        assert json.loads(result.output) == {"deleted": True, "id": "cft-1"}
        client.delete.assert_called_once_with(f"{_CUSTOM_TYPES_PATH}/cft-1")

    def test_refuses_without_confirmation(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client(_mock_response(200, [_CUSTOM_TYPE_JSON]))
        client.delete = AsyncMock()

        with patch("minitest_cli.commands.flow_types_write.ApiClient", return_value=client):
            result = _run_with_context(["delete", "payments"], settings, app_flag="app-1")

        assert result.exit_code == 1
        assert "--yes" in result.output
        assert "reset to 'other'" in result.output
        client.delete.assert_not_called()

    def test_unknown_name_exits_4(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client(_mock_response(200, [_CUSTOM_TYPE_JSON]))
        client.delete = AsyncMock()

        with patch("minitest_cli.commands.flow_types_write.ApiClient", return_value=client):
            result = _run_with_context(["delete", "nope", "--yes"], settings, app_flag="app-1")

        assert result.exit_code == 4
        client.delete.assert_not_called()


class TestFetchBuiltinFlowTypes:
    def test_returns_api_types_on_success(self, tmp_path):
        from minitest_cli.commands.flow_types_helpers import fetch_builtin_flow_types

        settings = _make_settings(tmp_path)
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = _TYPES
        with patch("minitest_cli.commands.flow_types_helpers.httpx.get", return_value=mock_resp):
            assert fetch_builtin_flow_types(settings) == _TYPES

    def test_network_error_exits_3(self, tmp_path):
        from click.exceptions import Exit

        from minitest_cli.commands.flow_types_helpers import fetch_builtin_flow_types

        settings = _make_settings(tmp_path)
        with (
            patch(
                "minitest_cli.commands.flow_types_helpers.httpx.get",
                side_effect=httpx.ConnectError("fail"),
            ),
            pytest.raises(Exit) as exc_info,
        ):
            fetch_builtin_flow_types(settings)
        assert exc_info.value.exit_code == 3

    def test_non_200_exits_3(self, tmp_path):
        from click.exceptions import Exit

        from minitest_cli.commands.flow_types_helpers import fetch_builtin_flow_types

        settings = _make_settings(tmp_path)
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 500
        with (
            patch("minitest_cli.commands.flow_types_helpers.httpx.get", return_value=mock_resp),
            pytest.raises(Exit) as exc_info,
        ):
            fetch_builtin_flow_types(settings)
        assert exc_info.value.exit_code == 3
