"""Tests for minitest_cli.commands.auth_api_key — mint, list, revoke."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from typer.testing import CliRunner

from minitest_cli.commands.auth_api_key import app as api_key_app
from minitest_cli.core.config import Settings

runner = CliRunner()

_TENANT = "11111111-1111-1111-1111-111111111111"
_KEY_ID = "22222222-2222-2222-2222-222222222222"
_PLAINTEXT = "mtk_live_abcdef0123456789"

_MINT_PAYLOAD = {
    "keyId": _KEY_ID,
    "name": "ci",
    "keyPrefix": "mtk_live_ab",
    "plaintextToken": _PLAINTEXT,
    "createdAt": "2024-01-01T00:00:00Z",
}

_LIST_PAYLOAD = [
    {
        "keyId": _KEY_ID,
        "name": "ci",
        "keyPrefix": "mtk_live_ab",
        "createdAt": "2024-01-01T00:00:00Z",
        "lastUsedAt": None,
        "createdBy": "user-1",
    }
]


def _make_settings(tmp_path, **overrides):
    defaults = {
        "config_dir": tmp_path,
        "token": "test-token",
        "supabase_url": "https://test.supabase.co",
        "supabase_publishable_key": "test-key",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _run_with_context(args, settings):
    # auth_api_key resolves settings via get_settings(), not the Typer context.
    with patch("minitest_cli.commands.auth_api_key.get_settings", return_value=settings):
        return runner.invoke(api_key_app, args)


def _mock_response(status_code=200, json_data=None):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = json.dumps(json_data) if json_data else ""
    resp.raise_for_status = MagicMock()
    return resp


def _mock_client(resp, method="post"):
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    setattr(client, method, AsyncMock(return_value=resp))
    return client


class TestMint:
    def test_human_output_prints_raw_token_without_ansi(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client(_mock_response(201, _MINT_PAYLOAD))

        with patch("minitest_cli.commands.auth_api_key.ApiClient", return_value=client):
            result = _run_with_context(["mint", "--tenant", _TENANT, "--name", "ci"], settings)

        assert result.exit_code == 0, result.output
        # The plaintext token is on stdout, verbatim, with no ANSI escapes.
        assert _PLAINTEXT in result.stdout
        token_line = next(line for line in result.stdout.splitlines() if _PLAINTEXT in line)
        assert token_line == _PLAINTEXT
        assert "\x1b[" not in token_line

    def test_warning_goes_to_stderr(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client(_mock_response(201, _MINT_PAYLOAD))

        with patch("minitest_cli.commands.auth_api_key.ApiClient", return_value=client):
            result = _run_with_context(["mint", "--tenant", _TENANT, "--name", "ci"], settings)

        assert result.exit_code == 0
        assert "Store this key now" not in result.stdout

    def test_json_output_includes_plaintext(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client(_mock_response(201, _MINT_PAYLOAD))

        with patch("minitest_cli.commands.auth_api_key.ApiClient", return_value=client):
            result = _run_with_context(
                ["mint", "--tenant", _TENANT, "--name", "ci", "--json"], settings
            )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert payload["plaintextToken"] == _PLAINTEXT
        assert payload["keyId"] == _KEY_ID

    def test_calls_correct_endpoint(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client(_mock_response(201, _MINT_PAYLOAD))

        with patch("minitest_cli.commands.auth_api_key.ApiClient", return_value=client):
            _run_with_context(["mint", "--tenant", _TENANT, "--name", "ci"], settings)

        client.post.assert_called_once_with(
            f"/api/v1/tenants/{_TENANT}/minitest-api-keys", json={"name": "ci"}
        )

    def test_refuses_when_only_api_key_set(self, tmp_path):
        settings = _make_settings(tmp_path, token=None, api_key="mtk_x")
        am_client = MagicMock()

        with patch("minitest_cli.commands.auth_api_key.ApiClient", return_value=am_client):
            result = _run_with_context(["mint", "--tenant", _TENANT, "--name", "ci"], settings)

        assert result.exit_code == 2
        am_client.assert_not_called()

    def test_rejects_non_uuid_tenant(self, tmp_path):
        settings = _make_settings(tmp_path)
        result = _run_with_context(["mint", "--tenant", "not-a-uuid", "--name", "ci"], settings)
        assert result.exit_code != 0


class TestList:
    def test_json_output(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client(_mock_response(200, _LIST_PAYLOAD), method="get")

        with patch("minitest_cli.commands.auth_api_key.ApiClient", return_value=client):
            result = _run_with_context(["list", "--tenant", _TENANT, "--json"], settings)

        assert result.exit_code == 0, result.output
        data = json.loads(result.stdout)
        assert data[0]["keyId"] == _KEY_ID

    def test_human_output_renders_table(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client(_mock_response(200, _LIST_PAYLOAD), method="get")

        with patch("minitest_cli.commands.auth_api_key.ApiClient", return_value=client):
            result = _run_with_context(["list", "--tenant", _TENANT], settings)

        assert result.exit_code == 0, result.output
        assert "mtk_live_ab" in result.stdout
        assert "—" in result.stdout  # placeholder for null lastUsedAt


class TestRevoke:
    def test_revoke_human(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client(_mock_response(204, None), method="delete")

        with patch("minitest_cli.commands.auth_api_key.ApiClient", return_value=client):
            result = _run_with_context(["revoke", "--tenant", _TENANT, "--key", _KEY_ID], settings)

        assert result.exit_code == 0, result.output
        client.delete.assert_called_once_with(
            f"/api/v1/tenants/{_TENANT}/minitest-api-keys/{_KEY_ID}"
        )

    def test_revoke_json(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client(_mock_response(204, None), method="delete")

        with patch("minitest_cli.commands.auth_api_key.ApiClient", return_value=client):
            result = _run_with_context(
                ["revoke", "--tenant", _TENANT, "--key", _KEY_ID, "--json"], settings
            )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert payload == {"revoked": True, "keyId": _KEY_ID}
