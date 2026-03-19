"""Tests for minitest_cli.commands.auth — CLI commands login, logout, status."""

import base64
import json
import time
from unittest.mock import patch

import typer
from typer.testing import CliRunner

from minitest_cli.commands.auth import app as auth_app
from minitest_cli.core.auth import Credentials, save_credentials
from minitest_cli.core.config import Settings

runner = CliRunner()


def _make_jwt(claims: dict) -> str:
    """Build a fake JWT (header.payload.signature) with the given claims."""
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return f"{header}.{payload}.fake-sig"


def _make_settings(tmp_path, **overrides):
    """Create a Settings instance using tmp_path as config dir."""
    defaults = {
        "config_dir": tmp_path,
        "token": None,
        "supabase_url": "https://test.supabase.co",
        "supabase_publishable_key": "test-publishable-key",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _make_credentials(**overrides):
    """Create a Credentials instance with sensible defaults."""
    defaults = {
        "access_token": "access-123",
        "refresh_token": "refresh-456",
        "expires_at": time.time() + 3600,
        "user_id": "user-789",
        "email": "test@example.com",
    }
    defaults.update(overrides)
    return Credentials(**defaults)


def _patch_context(settings, json_mode=False):
    """Patch typer.Context class attrs used by the commands."""
    return [
        patch.object(typer.Context, "settings", settings, create=True),
        patch.object(typer.Context, "json_mode", json_mode, create=True),
    ]


def _run_with_context(command, settings, json_mode=False, args=None):
    """Run an auth command with patched context."""
    patches = _patch_context(settings, json_mode)
    for p in patches:
        p.start()
    try:
        result = runner.invoke(auth_app, args or [command])
    finally:
        for p in patches:
            p.stop()
    return result


class TestLoginCommand:
    def test_login_exits_2_when_env_token_set(self, tmp_path):
        settings = _make_settings(tmp_path, token="env-token")
        result = _run_with_context("login", settings)
        assert result.exit_code == 2

    def test_login_calls_oauth_flow(self, tmp_path):
        settings = _make_settings(tmp_path)
        creds = _make_credentials()

        with patch("minitest_cli.commands.auth.oauth_pkce_login", return_value=creds) as mock_login:
            result = _run_with_context("login", settings)

        mock_login.assert_called_once_with(settings)
        assert result.exit_code == 0
        assert "test@example.com" in result.output


class TestLogoutCommand:
    def test_logout_exits_2_when_env_token_set(self, tmp_path):
        settings = _make_settings(tmp_path, token="env-token")
        result = _run_with_context("logout", settings)
        assert result.exit_code == 2

    def test_logout_clears_credentials(self, tmp_path):
        settings = _make_settings(tmp_path)
        save_credentials(settings, _make_credentials())
        creds_path = tmp_path / "credentials.json"
        assert creds_path.exists()

        result = _run_with_context("logout", settings)
        assert result.exit_code == 0
        assert not creds_path.exists()

    def test_logout_success_message(self, tmp_path):
        settings = _make_settings(tmp_path)
        result = _run_with_context("logout", settings)
        assert result.exit_code == 0


class TestStatusCommand:
    def test_status_env_token_json_with_jwt(self, tmp_path):
        token = _make_jwt({"sub": "uid-jwt", "email": "jwt@example.com", "exp": 1700000000})
        settings = _make_settings(tmp_path, token=token)
        result = _run_with_context("status", settings, json_mode=True)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["token_configured"] is True
        assert data["method"] == "env_token"
        assert data["user_id"] == "uid-jwt"
        assert data["email"] == "jwt@example.com"
        assert data["expires_at"] is not None

    def test_status_env_token_json_with_opaque_token(self, tmp_path):
        settings = _make_settings(tmp_path, token="opaque-api-key")
        result = _run_with_context("status", settings, json_mode=True)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["token_configured"] is True
        assert data["method"] == "env_token"
        assert data["user_id"] is None
        assert data["email"] is None
        assert data["expires_at"] is None

    def test_status_oauth_json(self, tmp_path):
        settings = _make_settings(tmp_path)
        creds = _make_credentials(
            user_id="uid-1",
            email="dev@example.com",
            expires_at=time.time() + 7200,
        )
        save_credentials(settings, creds)

        result = _run_with_context("status", settings, json_mode=True)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["token_configured"] is True
        assert data["method"] == "oauth"
        assert data["user_id"] == "uid-1"
        assert data["email"] == "dev@example.com"
        assert data["expires_at"] is not None

    def test_status_oauth_refreshes_expired_credentials(self, tmp_path):
        settings = _make_settings(tmp_path)
        # Store expired credentials (expires_at in the past)
        expired_creds = _make_credentials(
            user_id="uid-old",
            email="old@example.com",
            expires_at=time.time() - 100,
        )
        save_credentials(settings, expired_creds)

        refreshed_creds = _make_credentials(
            user_id="uid-old",
            email="old@example.com",
            expires_at=time.time() + 7200,
            access_token="new-access-token",
        )

        with patch(
            "minitest_cli.core.auth.refresh_token", return_value=refreshed_creds
        ) as mock_refresh:
            result = _run_with_context("status", settings, json_mode=True)

        assert mock_refresh.call_count >= 1
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["token_configured"] is True
        assert data["method"] == "oauth"

    def test_status_oauth_exits_2_when_refresh_fails(self, tmp_path):
        settings = _make_settings(tmp_path)
        expired_creds = _make_credentials(expires_at=time.time() - 100)
        save_credentials(settings, expired_creds)

        with patch("minitest_cli.core.auth.refresh_token", return_value=None):
            result = _run_with_context("status", settings, json_mode=False)

        assert result.exit_code == 2

    def test_status_not_authenticated_json(self, tmp_path):
        settings = _make_settings(tmp_path)
        result = _run_with_context("status", settings, json_mode=True)
        assert result.exit_code == 2
        data = json.loads(result.output)
        assert data["token_configured"] is False
        assert data["method"] == "none"

    def test_status_not_authenticated_human(self, tmp_path):
        settings = _make_settings(tmp_path)
        result = _run_with_context("status", settings, json_mode=False)
        assert result.exit_code == 2

    def test_status_env_token_human(self, tmp_path):
        token = _make_jwt({"sub": "uid-jwt", "email": "jwt@example.com", "exp": 1700000000})
        settings = _make_settings(tmp_path, token=token)
        result = _run_with_context("status", settings, json_mode=False)
        assert result.exit_code == 0
