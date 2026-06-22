"""Auth public API — token resolution and re-exports.

Consumers should import from this module:
    from minitest_cli.core.auth import load_token, Credentials, ...
"""

from __future__ import annotations

import base64
import json
import sys
from typing import Any, Literal, TypedDict

from minitest_cli.core.config import Settings
from minitest_cli.core.credentials import (
    Credentials,
    clear_credentials,
    get_credentials_path,
    load_credentials,
    save_credentials,
)
from minitest_cli.core.oauth import oauth_pkce_login, refresh_token
from minitest_cli.core.token_exchange import EXIT_CODE_AUTH_ERROR, auth_error

__all__ = [
    "AuthStatus",
    "EXIT_CODE_AUTH_ERROR",
    "AuthMethod",
    "Credentials",
    "clear_credentials",
    "decode_jwt_claims",
    "get_auth_method",
    "get_credentials_path",
    "load_credentials",
    "load_or_refresh_credentials",
    "load_token",
    "oauth_pkce_login",
    "require_auth",
    "refresh_token",
    "save_credentials",
]

AuthMethod = Literal["api_key", "env_token", "oauth", "none"]

_PRIORITY_WARNING_EMITTED = False


def _warn_priority_once(settings: Settings) -> None:
    global _PRIORITY_WARNING_EMITTED
    if _PRIORITY_WARNING_EMITTED:
        return
    if settings.token and settings.api_key:
        print(
            "[minitest] MINITEST_TOKEN and MINITEST_API_KEY are both set. "
            "MINITEST_TOKEN takes precedence. Unset one to silence this warning.",
            file=sys.stderr,
        )
        _PRIORITY_WARNING_EMITTED = True


class AuthStatus(TypedDict):
    """Typed shape for `minitest auth status` JSON output."""

    token_configured: bool
    method: AuthMethod
    user_id: str | None
    email: str | None
    expires_at: str | None


def load_or_refresh_credentials(settings: Settings) -> Credentials | None:
    """Load stored credentials, auto-refreshing if near expiry.

    Returns refreshed credentials, original credentials, or None.
    """
    creds = load_credentials(settings)
    if creds is None:
        return None
    if creds.is_expired:
        return refresh_token(settings, creds)
    return creds


def load_token(settings: Settings) -> str:
    """Load the auth token, preferring MINITEST_TOKEN, then MINITEST_API_KEY, then OAuth."""
    _warn_priority_once(settings)

    if settings.token:
        return settings.token

    if settings.api_key:
        return settings.api_key.get_secret_value()

    creds = load_or_refresh_credentials(settings)
    if creds is not None:
        return creds.access_token

    auth_error(
        "Not authenticated. Set MINITEST_API_KEY, run `minitest auth login`, or set MINITEST_TOKEN."
    )


def require_auth(settings: Settings) -> str:
    """Ensure the user is authenticated, returning the bearer token.

    Triggers token refresh if credentials are near expiry.
    Exits with code 2 if not authenticated.
    """
    return load_token(settings)


def get_auth_method(settings: Settings) -> AuthMethod:
    """Return the active auth method: 'env_token', 'oauth', or 'none'.

    For OAuth, validates that stored credentials are usable (not expired,
    or successfully refreshed). Returns 'none' if credentials exist but
    are expired and refresh fails.
    """
    if settings.token:
        return "env_token"
    if settings.api_key:
        return "api_key"
    if load_or_refresh_credentials(settings) is not None:
        return "oauth"
    return "none"


def decode_jwt_claims(token: str) -> dict[str, Any]:
    """Decode JWT payload without verification. Returns empty dict on failure."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:  # noqa: BLE001
        return {}
