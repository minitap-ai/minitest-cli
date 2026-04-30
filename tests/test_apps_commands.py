"""Tests for minitest_cli.commands.apps — CLI commands list and create."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import typer
from typer.testing import CliRunner

from minitest_cli.commands.apps import app as apps_app
from minitest_cli.core.config import Settings
from minitest_cli.models.app import TenantResponse

runner = CliRunner()

_APPS_DATA = {
    "apps": [
        {"id": "aaa-111", "name": "My App", "tenantId": "t-1"},
        {"id": "bbb-222", "name": "Other App", "tenantId": "t-1"},
    ]
}


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


class TestListApps:
    def test_json_output(self, tmp_path):
        settings = _make_settings(tmp_path)
        resp = _mock_response(200, _APPS_DATA)
        client = _mock_client(resp)

        with patch("minitest_cli.commands.apps.ApiClient", return_value=client):
            result = _run_with_context(["list"], settings, json_mode=True)

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 2
        assert data[0]["id"] == "aaa-111"
        assert data[0]["name"] == "My App"
        assert data[1]["id"] == "bbb-222"

    def test_human_output(self, tmp_path):
        settings = _make_settings(tmp_path)
        resp = _mock_response(200, _APPS_DATA)
        client = _mock_client(resp)

        with patch("minitest_cli.commands.apps.ApiClient", return_value=client):
            result = _run_with_context(["list"], settings)

        assert result.exit_code == 0
        assert "My App" in result.output
        assert "Other App" in result.output
        assert "aaa-111" in result.output

    def test_empty_list(self, tmp_path):
        settings = _make_settings(tmp_path)
        resp = _mock_response(200, {"apps": []})
        client = _mock_client(resp)

        with patch("minitest_cli.commands.apps.ApiClient", return_value=client):
            result = _run_with_context(["list"], settings, json_mode=True)

        assert result.exit_code == 0
        assert json.loads(result.output) == []

    def test_api_error(self, tmp_path):
        settings = _make_settings(tmp_path)
        resp = _mock_response(500, {"detail": "Internal error"})
        client = _mock_client(resp)

        with patch("minitest_cli.commands.apps.ApiClient", return_value=client):
            result = _run_with_context(["list"], settings)

        assert result.exit_code == 3

    def test_network_error(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.get = AsyncMock(side_effect=httpx.ConnectError("connection refused"))

        with patch("minitest_cli.commands.apps.ApiClient", return_value=client):
            result = _run_with_context(["list"], settings)

        assert result.exit_code == 3

    def test_auth_required(self, tmp_path):
        settings = _make_settings(tmp_path, token=None)
        result = _run_with_context(["list"], settings)
        assert result.exit_code == 2

    def test_calls_correct_endpoint(self, tmp_path):
        settings = _make_settings(tmp_path)
        resp = _mock_response(200, _APPS_DATA)
        client = _mock_client(resp)

        with patch("minitest_cli.commands.apps.ApiClient", return_value=client):
            _run_with_context(["list"], settings)

        client.get.assert_called_once_with("/api/v1/apps")


# ---------------------------------------------------------------------------
# `apps create` tests
# ---------------------------------------------------------------------------

_NOW = datetime(2024, 1, 1, tzinfo=UTC).isoformat()
_APP_RECORD = {
    "id": "app-xyz",
    "tenantId": "t-1",
    "name": "Foo",
    "slug": "foo",
    "description": "A demo",
    "iconUrl": None,
    "isDefault": False,
    "aiPreferences": {},
    "sourceRepoKnowledgeId": None,
    "sourceDefaultBranch": None,
    "sourceFolder": None,
    "repositories": [],
    "createdAt": _NOW,
    "updatedAt": _NOW,
}


def _mock_apps_manager_client(resp):
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.upload_form = AsyncMock(return_value=resp)
    return client


class TestCreateApp:
    def test_missing_name_is_usage_error(self, tmp_path):
        settings = _make_settings(tmp_path)
        # No backend mocks: the command must fail before contacting the network.
        with patch("minitest_cli.commands.apps_helpers.AppsManagerClient") as am_client:
            result = _run_with_context(["create", "--tenant", "t-1"], settings)

        assert result.exit_code != 0
        am_client.assert_not_called()

    def test_explicit_tenant_happy_path_prints_id(self, tmp_path):
        settings = _make_settings(tmp_path)
        resp = _mock_response(201, _APP_RECORD)
        client = _mock_apps_manager_client(resp)

        with patch("minitest_cli.commands.apps_helpers.AppsManagerClient", return_value=client):
            result = _run_with_context(
                ["create", "--tenant", "t-1", "--name", "Foo"],
                settings,
            )

        assert result.exit_code == 0, result.output
        # Only the id should appear on stdout (success message goes to stderr).
        assert "app-xyz" in result.output
        # Endpoint and form data check.
        client.upload_form.assert_called_once()
        args, kwargs = client.upload_form.call_args
        assert args[0] == "/api/v1/tenants/t-1/apps"
        assert kwargs["data"] == {"name": "Foo"}
        assert kwargs["files"] == {}

    def test_json_mode_prints_full_record(self, tmp_path):
        settings = _make_settings(tmp_path)
        resp = _mock_response(201, _APP_RECORD)
        client = _mock_apps_manager_client(resp)

        with patch("minitest_cli.commands.apps_helpers.AppsManagerClient", return_value=client):
            result = _run_with_context(
                ["create", "--tenant", "t-1", "--name", "Foo"],
                settings,
                json_mode=True,
            )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["id"] == "app-xyz"
        assert payload["tenantId"] == "t-1"
        assert payload["slug"] == "foo"

    def test_passes_optional_fields(self, tmp_path):
        settings = _make_settings(tmp_path)
        resp = _mock_response(201, _APP_RECORD)
        client = _mock_apps_manager_client(resp)

        with patch("minitest_cli.commands.apps_helpers.AppsManagerClient", return_value=client):
            result = _run_with_context(
                [
                    "create",
                    "--tenant",
                    "t-1",
                    "--name",
                    "Foo",
                    "--description",
                    "A demo",
                    "--slug",
                    "custom-slug",
                ],
                settings,
            )

        assert result.exit_code == 0, result.output
        _, kwargs = client.upload_form.call_args
        assert kwargs["data"] == {
            "name": "Foo",
            "description": "A demo",
            "slug": "custom-slug",
        }

    def test_auto_resolves_single_tenant(self, tmp_path):
        settings = _make_settings(tmp_path)
        resp = _mock_response(201, _APP_RECORD)
        client = _mock_apps_manager_client(resp)
        single = [TenantResponse(id="t-1", name="Solo")]

        with (
            patch(
                "minitest_cli.commands.apps.fetch_user_tenants",
                AsyncMock(return_value=single),
            ),
            patch("minitest_cli.commands.apps_helpers.AppsManagerClient", return_value=client),
        ):
            result = _run_with_context(
                ["create", "--name", "Foo"],
                settings,
            )

        assert result.exit_code == 0, result.output
        _, kwargs = client.upload_form.call_args
        assert "t-1" in client.upload_form.call_args.args[0]
        assert kwargs["data"]["name"] == "Foo"

    def test_multi_tenant_non_tty_errors(self, tmp_path):
        settings = _make_settings(tmp_path)
        many = [
            TenantResponse(id="t-1", name="Alpha"),
            TenantResponse(id="t-2", name="Beta"),
        ]
        am_client = MagicMock()

        with (
            patch(
                "minitest_cli.commands.apps.fetch_user_tenants",
                AsyncMock(return_value=many),
            ),
            patch("minitest_cli.core.tenants._stdin_is_tty", return_value=False),
            patch(
                "minitest_cli.commands.apps_helpers.AppsManagerClient",
                return_value=am_client,
            ),
        ):
            result = _run_with_context(["create", "--name", "Foo"], settings)

        assert result.exit_code == 1
        # Backend must NOT have been contacted.
        am_client.assert_not_called()

    def test_multi_tenant_tty_prompt_uses_choice(self, tmp_path):
        settings = _make_settings(tmp_path)
        resp = _mock_response(201, _APP_RECORD)
        client = _mock_apps_manager_client(resp)
        many = [
            TenantResponse(id="t-1", name="Alpha"),
            TenantResponse(id="t-2", name="Beta"),
        ]

        with (
            patch(
                "minitest_cli.commands.apps.fetch_user_tenants",
                AsyncMock(return_value=many),
            ),
            patch("minitest_cli.core.tenants._stdin_is_tty", return_value=True),
            patch("minitest_cli.core.tenants.typer.prompt", return_value="2"),
            patch("minitest_cli.commands.apps_helpers.AppsManagerClient", return_value=client),
        ):
            result = _run_with_context(["create", "--name", "Foo"], settings)

        assert result.exit_code == 0, result.output
        # Tenant 2 (= t-2) must be the one used.
        assert client.upload_form.call_args.args[0] == "/api/v1/tenants/t-2/apps"

    def test_zero_tenants_errors_clearly(self, tmp_path):
        settings = _make_settings(tmp_path)
        am_client = MagicMock()

        with (
            patch(
                "minitest_cli.commands.apps.fetch_user_tenants",
                AsyncMock(return_value=[]),
            ),
            patch(
                "minitest_cli.commands.apps_helpers.AppsManagerClient",
                return_value=am_client,
            ),
        ):
            result = _run_with_context(["create", "--name", "Foo"], settings)

        assert result.exit_code == 1
        am_client.assert_not_called()

    def test_backend_validation_error_maps_to_exit_1(self, tmp_path):
        settings = _make_settings(tmp_path)
        resp = _mock_response(400, {"detail": "name is required"})
        client = _mock_apps_manager_client(resp)

        with patch("minitest_cli.commands.apps_helpers.AppsManagerClient", return_value=client):
            result = _run_with_context(
                ["create", "--tenant", "t-1", "--name", "Foo"],
                settings,
            )

        assert result.exit_code == 1

    def test_backend_5xx_maps_to_exit_3(self, tmp_path):
        settings = _make_settings(tmp_path)
        resp = _mock_response(503, {"detail": "service unavailable"})
        client = _mock_apps_manager_client(resp)

        with patch("minitest_cli.commands.apps_helpers.AppsManagerClient", return_value=client):
            result = _run_with_context(
                ["create", "--tenant", "t-1", "--name", "Foo"],
                settings,
            )

        assert result.exit_code == 3

    def test_auth_failure_maps_to_exit_1_no_traceback(self, tmp_path):
        settings = _make_settings(tmp_path)
        resp = _mock_response(401, {"detail": "Invalid or expired token"})
        client = _mock_apps_manager_client(resp)

        with patch("minitest_cli.commands.apps_helpers.AppsManagerClient", return_value=client):
            result = _run_with_context(
                ["create", "--tenant", "t-1", "--name", "Foo"],
                settings,
            )

        assert result.exit_code == 1
        # No raw stack trace in user output.
        assert "Traceback" not in result.output

    def test_no_token_blocks_before_backend(self, tmp_path):
        settings = _make_settings(tmp_path, token=None)
        am_client = MagicMock()
        with patch(
            "minitest_cli.commands.apps_helpers.AppsManagerClient",
            return_value=am_client,
        ):
            result = _run_with_context(
                ["create", "--tenant", "t-1", "--name", "Foo"],
                settings,
            )

        assert result.exit_code == 2
        am_client.assert_not_called()

    def test_network_error_maps_to_exit_3(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.upload_form = AsyncMock(side_effect=httpx.ConnectError("boom"))

        with patch("minitest_cli.commands.apps_helpers.AppsManagerClient", return_value=client):
            result = _run_with_context(
                ["create", "--tenant", "t-1", "--name", "Foo"],
                settings,
            )

        assert result.exit_code == 3
