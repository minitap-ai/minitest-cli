"""Supabase token exchange and persistence helpers."""

from __future__ import annotations

import sys
import time
from typing import Any, NoReturn

import httpx

from minitest_cli.core.config import Settings
from minitest_cli.core.credentials import Credentials, save_credentials

EXIT_CODE_AUTH_ERROR = 2


def require_supabase_url(settings: Settings) -> str:
    """Return the supabase URL or exit with code 2."""
    if settings.supabase_url:
        return settings.supabase_url.rstrip("/")
    auth_error("MINITEST_SUPABASE_URL is not set. Set it in your environment or .env file.")


def get_apikey_header(settings: Settings) -> str:
    """Return the Supabase publishable key for the apikey header.

    Supabase requires an `apikey` header on all auth endpoints.
    """
    if settings.supabase_publishable_key:
        return settings.supabase_publishable_key
    auth_error(
        "MINITEST_SUPABASE_PUBLISHABLE_KEY is not set. Set it in your environment or .env file."
    )


def parse_and_save_token_response(settings: Settings, data: dict[str, Any]) -> Credentials | None:
    """Parse a Supabase token response and persist credentials."""
    try:
        user = data.get("user", {})
        if not isinstance(user, dict):
            user = {}
        expires_in = data.get("expires_in", 3600)
        creds = Credentials(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            expires_at=time.time() + int(expires_in),
            user_id=user.get("id", ""),
            email=user.get("email", ""),
        )
        save_credentials(settings, creds)
        return creds
    except (KeyError, TypeError, ValueError):
        return None


def register_oauth_client(supabase_url: str, redirect_uri: str) -> str:
    """Dynamically register an OAuth2 client with Supabase and return the client_id."""
    register_url = f"{supabase_url}/auth/v1/oauth/clients/register"
    try:
        resp = httpx.post(
            register_url,
            json={
                "client_name": "minitest-cli",
                "redirect_uris": [redirect_uri],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "none",
            },
            headers={"Content-Type": "application/json"},
            timeout=15.0,
        )
    except httpx.HTTPError as exc:
        auth_error(f"Failed to register OAuth client: {exc}")

    if resp.status_code not in (200, 201):
        auth_error(f"OAuth client registration failed: {resp.text}")

    try:
        data = resp.json()
    except ValueError:
        auth_error(
            f"OAuth client registration returned invalid response "
            f"(HTTP {resp.status_code}): {resp.text}"
        )

    client_id: str | None = data.get("client_id")
    if not client_id:
        auth_error("OAuth client registration returned no client_id.")
    return client_id  # type: ignore[return-value]


def auth_error(message: str) -> NoReturn:
    """Print auth error to stderr and exit with code 2."""
    print(f"Error: {message}", file=sys.stderr)  # noqa: T201
    raise SystemExit(EXIT_CODE_AUTH_ERROR)
