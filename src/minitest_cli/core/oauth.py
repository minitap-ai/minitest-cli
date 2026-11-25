"""OAuth PKCE login flow via Supabase OAuth2 server, and token refresh."""

from __future__ import annotations

import importlib.resources
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler
from threading import Event
from typing import Any

import httpx

from minitest_cli.core.config import Settings
from minitest_cli.core.credentials import Credentials
from minitest_cli.core.oauth_client import (
    announce_authorize_url,
    bind_callback_server,
    pkce_pair,
    redirect_uri_for,
    resolve_client_id,
)
from minitest_cli.core.token_exchange import (
    SessionRevokedError,
    auth_error,
    parse_and_save_token_response,
    parse_token_response,
)

_ASSETS = importlib.resources.files("minitest_cli.assets")
REFRESH_ATTEMPTS = 3
REFRESH_RETRY_DELAY_SECONDS = 1.0
DEFAULT_LOGIN_TIMEOUT_SECONDS = 120


def refresh_token(settings: Settings, creds: Credentials) -> Credentials | None:
    """Refresh an expired access token; the caller decides whether to persist the result.

    OAuth sessions must refresh against the same client that created them, so a
    persisted client_id is required. Network errors and 5xx are retried, then None
    is returned. Raises SessionRevokedError when the token can never succeed
    (missing client_id, or a 4xx rejection) so callers can clear it and re-login.
    """
    if not settings.supabase_url or not settings.supabase_publishable_key:
        return None
    if not creds.client_id:
        raise SessionRevokedError

    supabase_url = settings.supabase_url.rstrip("/")
    for attempt in range(REFRESH_ATTEMPTS):
        if attempt:
            time.sleep(REFRESH_RETRY_DELAY_SECONDS * attempt)
        try:
            response = httpx.post(
                f"{supabase_url}/auth/v1/oauth/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": creds.refresh_token,
                    "client_id": creds.client_id,
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "apikey": settings.supabase_publishable_key,
                },
                timeout=15.0,
            )
        except httpx.HTTPError:
            continue
        if 400 <= response.status_code < 500:
            raise SessionRevokedError
        if response.status_code >= 500:
            continue
        try:
            data = response.json()
        except ValueError:
            return None
        if not isinstance(data, dict):
            return None
        return parse_token_response(data, creds.client_id)
    return None


def oauth_pkce_login(
    settings: Settings,
    *,
    open_browser: bool = True,
    timeout: int = DEFAULT_LOGIN_TIMEOUT_SECONDS,
    json_mode: bool = False,
) -> Credentials:
    """Run the full OAuth PKCE login flow via Supabase's OAuth2 server."""
    supabase_url = settings.supabase_url.rstrip("/")

    code_verifier, code_challenge = pkce_pair()
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

    server = bind_callback_server(_CallbackHandler)
    port = server.server_address[1]
    redirect_uri = redirect_uri_for(port)
    client_id = resolve_client_id(settings, supabase_url, port)

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

    announce_authorize_url(authorize_url, open_browser=open_browser, json_mode=json_mode)
    if open_browser:
        webbrowser.open(authorize_url)

    deadline = time.time() + timeout
    while not ready_event.is_set():
        remaining = deadline - time.time()
        if remaining <= 0:
            server.server_close()
            auth_error(f"OAuth login timed out after {timeout} seconds.")
        server.timeout = min(5.0, remaining)
        server.handle_request()

    server.server_close()

    if auth_code_holder["error"]:
        auth_error(f"OAuth login failed: {auth_code_holder['error']}")

    auth_code = auth_code_holder["code"]
    if not auth_code:
        auth_error("No authorization code received.")

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

    creds = parse_and_save_token_response(settings, response_data, client_id)
    if creds is None:
        auth_error("Failed to parse token response.")

    assert creds is not None
    return creds
