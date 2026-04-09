"""OAuth PKCE login flow via Supabase OAuth2 server, and token refresh."""

from __future__ import annotations

import base64
import hashlib
import importlib.resources
import secrets
import sys
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Event
from typing import Any

import httpx

from minitest_cli.core.config import Settings
from minitest_cli.core.credentials import Credentials
from minitest_cli.core.token_exchange import (
    auth_error,
    parse_and_save_token_response,
    register_oauth_client,
)

_ASSETS = importlib.resources.files("minitest_cli.assets")


def refresh_token(settings: Settings, creds: Credentials) -> Credentials | None:
    """Refresh an expired access token using the refresh token.

    Returns updated credentials (also saved to disk), or None on failure.
    """
    if not settings.supabase_url or not settings.supabase_publishable_key:
        return None

    supabase_url = settings.supabase_url.rstrip("/")
    try:
        response = httpx.post(
            f"{supabase_url}/auth/v1/token?grant_type=refresh_token",
            json={"refresh_token": creds.refresh_token},
            headers={
                "Content-Type": "application/json",
                "apikey": settings.supabase_publishable_key,
            },
            timeout=15.0,
        )
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError):
        return None

    if not isinstance(data, dict):
        return None

    return parse_and_save_token_response(settings, data)


def oauth_pkce_login(settings: Settings) -> Credentials:
    """Run the full OAuth PKCE login flow via Supabase's OAuth2 server.

    Steps:
      1. Start local callback server
      2. Dynamically register an OAuth2 client with Supabase
      3. Generate PKCE code verifier + challenge
      4. Open browser to Supabase authorize endpoint (shows hosted sign-in page)
      5. Wait for callback with authorization code
      6. Exchange code + verifier for tokens at Supabase token endpoint
      7. Save and return credentials
    """
    supabase_url = settings.supabase_url.rstrip("/")

    # PKCE challenge: base64url(sha256(verifier)) without padding
    code_verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

    # Start callback server
    auth_code_holder: dict[str, str | None] = {"code": None, "error": None}
    ready_event = Event()

    class _CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            code = params.get("code", [None])[0]
            error = params.get("error_description", params.get("error", [None]))[0]

            if code:
                auth_code_holder["code"] = code
                self._respond("Login successful!", is_success=True)
            else:
                auth_code_holder["error"] = error or "Unknown error"
                self._respond(f"Login failed: {auth_code_holder['error']}", is_success=False)

            ready_event.set()

        def _respond(self, message: str, *, is_success: bool) -> None:
            template = _ASSETS.joinpath("callback.html").read_text(encoding="utf-8")
            html = template.replace("{{message}}", message).replace(
                "{{status_class}}", "success" if is_success else "error"
            )
            encoded = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            pass  # silence HTTP logs

    server = HTTPServer(("127.0.0.1", 0), _CallbackHandler)
    port = server.server_address[1]
    redirect_uri = f"http://127.0.0.1:{port}/callback"

    # Register OAuth client with Supabase (dynamic client registration)
    client_id = register_oauth_client(supabase_url, redirect_uri)

    # Build authorize URL — Supabase's OAuth2 server shows its hosted sign-in page
    authorize_params = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "scope": "openid email profile",
        }
    )
    authorize_url = f"{supabase_url}/auth/v1/oauth/authorize?{authorize_params}"

    print("Opening browser for authentication...", file=sys.stderr)  # noqa: T201
    print(f"If the browser doesn't open, visit:\n{authorize_url}", file=sys.stderr)  # noqa: T201
    webbrowser.open(authorize_url)

    # Wait for callback with absolute deadline
    deadline = time.time() + 120
    server.timeout = 5  # poll interval; overall limit enforced by deadline
    while not ready_event.is_set():
        if time.time() >= deadline:
            server.server_close()
            auth_error("OAuth login timed out after 2 minutes.")
        server.handle_request()

    server.server_close()

    if auth_code_holder["error"]:
        auth_error(f"OAuth login failed: {auth_code_holder['error']}")

    auth_code = auth_code_holder["code"]
    if not auth_code:
        auth_error("No authorization code received.")

    # Exchange code for tokens at Supabase's OAuth2 token endpoint
    assert auth_code is not None  # for type narrowing
    try:
        token_response = httpx.post(
            f"{supabase_url}/auth/v1/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": auth_code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "code_verifier": code_verifier,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15.0,
        )
    except httpx.HTTPError as exc:
        auth_error(f"Token exchange request failed: {exc}")

    if token_response.status_code != 200:
        auth_error(f"Token exchange failed: {token_response.text}")

    try:
        response_data = token_response.json()
    except ValueError:
        auth_error("Token exchange returned invalid JSON.")

    if not isinstance(response_data, dict):
        auth_error("Token exchange returned unexpected response format.")

    creds = parse_and_save_token_response(settings, response_data)
    if creds is None:
        auth_error("Failed to parse token response.")

    assert creds is not None
    return creds
