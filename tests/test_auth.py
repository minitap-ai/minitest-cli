"""Tests for minitest_cli.core.auth — credentials, token loading, and refresh."""

import json
import time
from unittest.mock import MagicMock, patch

import httpx
import pytest

from minitest_cli.core.auth import (
    Credentials,
    EXIT_CODE_AUTH_ERROR,
    clear_credentials,
    decode_jwt_claims,
    get_auth_method,
    get_credentials_path,
    load_credentials,
    load_token,
    refresh_token,
    save_credentials,
)
from minitest_cli.core.config import Settings
from minitest_cli.core.credentials import REFRESH_BUFFER_SECONDS


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
        "expires_at": time.time() + 3600,  # 1 hour from now
        "user_id": "user-789",
        "email": "test@example.com",
    }
    defaults.update(overrides)
    return Credentials(**defaults)


class TestCredentialsModel:
    def test_is_expired_future_token(self):
        creds = _make_credentials(expires_at=time.time() + 3600)
        assert creds.is_expired is False

    def test_is_expired_past_token(self):
        creds = _make_credentials(expires_at=time.time() - 60)
        assert creds.is_expired is True

    def test_is_expired_within_buffer(self):
        """Token within the 5-minute refresh buffer should be considered expired."""
        creds = _make_credentials(expires_at=time.time() + REFRESH_BUFFER_SECONDS - 10)
        assert creds.is_expired is True

    def test_is_expired_just_outside_buffer(self):
        """Token just outside the 5-minute buffer should NOT be considered expired."""
        creds = _make_credentials(expires_at=time.time() + REFRESH_BUFFER_SECONDS + 60)
        assert creds.is_expired is False


class TestCredentialFileIO:
    def test_get_credentials_path(self, tmp_path):
        settings = _make_settings(tmp_path)
        path = get_credentials_path(settings)
        assert path == tmp_path / "credentials.json"

    def test_save_and_load_credentials(self, tmp_path):
        settings = _make_settings(tmp_path)
        creds = _make_credentials()
        save_credentials(settings, creds)

        loaded = load_credentials(settings)
        assert loaded is not None
        assert loaded.access_token == creds.access_token
        assert loaded.refresh_token == creds.refresh_token
        assert loaded.user_id == creds.user_id
        assert loaded.email == creds.email

    def test_save_credentials_permissions(self, tmp_path):
        settings = _make_settings(tmp_path)
        save_credentials(settings, _make_credentials())
        path = get_credentials_path(settings)
        # 0o600 = owner read/write only
        assert oct(path.stat().st_mode & 0o777) == oct(0o600)

    def test_load_credentials_missing_file(self, tmp_path):
        settings = _make_settings(tmp_path)
        assert load_credentials(settings) is None

    def test_load_credentials_invalid_json(self, tmp_path):
        settings = _make_settings(tmp_path)
        path = get_credentials_path(settings)
        path.write_text("not valid json{{{")
        assert load_credentials(settings) is None

    def test_load_credentials_invalid_schema(self, tmp_path):
        settings = _make_settings(tmp_path)
        path = get_credentials_path(settings)
        path.write_text(json.dumps({"wrong": "fields"}))
        assert load_credentials(settings) is None

    def test_clear_credentials_removes_file(self, tmp_path):
        settings = _make_settings(tmp_path)
        save_credentials(settings, _make_credentials())
        assert get_credentials_path(settings).exists()

        clear_credentials(settings)
        assert not get_credentials_path(settings).exists()

    def test_clear_credentials_no_file(self, tmp_path):
        """Clearing when no file exists should not raise."""
        settings = _make_settings(tmp_path)
        clear_credentials(settings)  # should be a no-op


class TestGetAuthMethod:
    def test_env_token_takes_priority(self, tmp_path):
        settings = _make_settings(tmp_path, token="env-token-123")
        # Even if credentials file exists, env_token wins
        save_credentials(settings, _make_credentials())
        assert get_auth_method(settings) == "env_token"

    def test_oauth_when_credentials_exist(self, tmp_path):
        settings = _make_settings(tmp_path)
        save_credentials(settings, _make_credentials())
        assert get_auth_method(settings) == "oauth"

    def test_none_when_no_auth(self, tmp_path):
        settings = _make_settings(tmp_path)
        assert get_auth_method(settings) == "none"

    def test_none_when_credentials_expired_and_refresh_fails(self, tmp_path):
        settings = _make_settings(tmp_path)
        expired_creds = _make_credentials(expires_at=time.time() - 100)
        save_credentials(settings, expired_creds)
        with patch("minitest_cli.core.auth.refresh_token", return_value=None):
            assert get_auth_method(settings) == "none"

    def test_oauth_when_credentials_expired_but_refresh_succeeds(self, tmp_path):
        settings = _make_settings(tmp_path)
        expired_creds = _make_credentials(expires_at=time.time() - 100)
        save_credentials(settings, expired_creds)
        refreshed = _make_credentials(expires_at=time.time() + 7200)
        with patch("minitest_cli.core.auth.refresh_token", return_value=refreshed):
            assert get_auth_method(settings) == "oauth"


class TestLoadToken:
    def test_returns_env_token(self, tmp_path):
        settings = _make_settings(tmp_path, token="my-env-token")
        assert load_token(settings) == "my-env-token"

    def test_returns_stored_access_token(self, tmp_path):
        settings = _make_settings(tmp_path)
        save_credentials(settings, _make_credentials(access_token="stored-tok"))
        assert load_token(settings) == "stored-tok"

    def test_refreshes_expired_token(self, tmp_path):
        settings = _make_settings(tmp_path)
        expired_creds = _make_credentials(expires_at=time.time() - 60)
        save_credentials(settings, expired_creds)

        refreshed = _make_credentials(access_token="refreshed-tok")
        with patch("minitest_cli.core.auth.refresh_token", return_value=refreshed):
            assert load_token(settings) == "refreshed-tok"

    def test_exits_when_no_auth(self, tmp_path):
        settings = _make_settings(tmp_path)
        with pytest.raises(SystemExit) as exc_info:
            load_token(settings)
        assert exc_info.value.code == EXIT_CODE_AUTH_ERROR

    def test_exits_when_refresh_fails(self, tmp_path):
        settings = _make_settings(tmp_path)
        expired_creds = _make_credentials(expires_at=time.time() - 60)
        save_credentials(settings, expired_creds)

        with patch("minitest_cli.core.auth.refresh_token", return_value=None):
            with pytest.raises(SystemExit) as exc_info:
                load_token(settings)
            assert exc_info.value.code == EXIT_CODE_AUTH_ERROR


class TestRefreshToken:
    def test_successful_refresh(self, tmp_path):
        settings = _make_settings(tmp_path)
        old_creds = _make_credentials(expires_at=time.time() - 60)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_in": 3600,
            "user": {"id": "user-789", "email": "test@example.com"},
        }
        mock_response.raise_for_status = MagicMock()

        with patch("minitest_cli.core.oauth.httpx.post", return_value=mock_response):
            result = refresh_token(settings, old_creds)

        assert result is not None
        assert result.access_token == "new-access"
        assert result.refresh_token == "new-refresh"
        # Credentials should be saved to disk
        loaded = load_credentials(settings)
        assert loaded is not None
        assert loaded.access_token == "new-access"

    def test_returns_none_on_http_error(self, tmp_path):
        settings = _make_settings(tmp_path)
        old_creds = _make_credentials()

        with patch(
            "minitest_cli.core.oauth.httpx.post",
            side_effect=httpx.HTTPStatusError("401", request=MagicMock(), response=MagicMock()),
        ):
            assert refresh_token(settings, old_creds) is None

    def test_returns_none_without_supabase_url(self, tmp_path):
        settings = _make_settings(tmp_path, supabase_url="")
        assert refresh_token(settings, _make_credentials()) is None

    def test_returns_none_without_publishable_key(self, tmp_path):
        settings = _make_settings(tmp_path, supabase_publishable_key="")
        assert refresh_token(settings, _make_credentials()) is None

    def test_sends_correct_request(self, tmp_path):
        settings = _make_settings(tmp_path)
        old_creds = _make_credentials(refresh_token="my-refresh")

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "new",
            "refresh_token": "new-r",
            "expires_in": 3600,
            "user": {"id": "u", "email": "e@e.com"},
        }
        mock_response.raise_for_status = MagicMock()

        with patch("minitest_cli.core.oauth.httpx.post", return_value=mock_response) as mock_post:
            refresh_token(settings, old_creds)

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert "grant_type=refresh_token" in call_args.args[0]
        assert call_args.kwargs["json"]["refresh_token"] == "my-refresh"
        assert call_args.kwargs["headers"]["apikey"] == "test-publishable-key"


class TestDecodeJwtClaims:
    def _make_jwt(self, claims: dict) -> str:
        import base64

        header = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode()
        payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
        return f"{header}.{payload}.fake-sig"

    def test_decodes_valid_jwt(self):
        token = self._make_jwt({"sub": "user-1", "email": "a@b.com", "exp": 9999999999})
        claims = decode_jwt_claims(token)
        assert claims["sub"] == "user-1"
        assert claims["email"] == "a@b.com"
        assert claims["exp"] == 9999999999

    def test_returns_empty_dict_for_opaque_token(self):
        assert decode_jwt_claims("opaque-api-key") == {}

    def test_returns_empty_dict_for_empty_string(self):
        assert decode_jwt_claims("") == {}

    def test_returns_empty_dict_for_malformed_jwt(self):
        assert decode_jwt_claims("not.valid.base64!!!") == {}
