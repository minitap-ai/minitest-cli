"""Reuse one registered OAuth client per auth server instead of registering on every login."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import secrets
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx

from minitest_cli.core.config import Settings
from minitest_cli.core.token_exchange import register_oauth_client

# Supabase matches redirect URIs exactly (port included), so the reusable client registers
# a fixed set of loopback ports; at most 10 redirect URIs are allowed per client.
CALLBACK_PORTS = tuple(range(41721, 41726))
CLIENT_CACHE_FILE = "oauth_client.json"


def pkce_pair() -> tuple[str, str]:
    """A PKCE code verifier and its S256 challenge."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def announce_authorize_url(authorize_url: str, *, open_browser: bool, json_mode: bool) -> None:
    if json_mode:
        print(json.dumps({"authorize_url": authorize_url}), flush=True)  # noqa: T201
    if open_browser:
        print("Opening browser for authentication...", file=sys.stderr)  # noqa: T201
        print(f"If the browser doesn't open, visit:\n{authorize_url}", file=sys.stderr)  # noqa: T201
    else:
        print(f"Open this URL in a browser on this machine:\n{authorize_url}", file=sys.stderr)  # noqa: T201


def redirect_uri_for(port: int) -> str:
    return f"http://127.0.0.1:{port}/callback"


class _CallbackServer(HTTPServer):
    # On Windows SO_REUSEADDR lets a second login bind a port already listening and steal the code.
    allow_reuse_address = sys.platform != "win32"


def bind_callback_server(handler: type[BaseHTTPRequestHandler]) -> HTTPServer:
    """Listen on the first free fixed port, or on a random one when they are all taken."""
    for port in CALLBACK_PORTS:
        with contextlib.suppress(OSError):
            return _CallbackServer(("127.0.0.1", port), handler)
    return _CallbackServer(("127.0.0.1", 0), handler)


def resolve_client_id(settings: Settings, supabase_url: str, port: int) -> str:
    """Return a client allowed to redirect to this port, registering one only when needed."""
    if port not in CALLBACK_PORTS:
        return register_oauth_client(supabase_url, [redirect_uri_for(port)])

    cache = _load_cache(settings)
    cached = cache.get(supabase_url)
    if cached and _client_accepts(supabase_url, cached, redirect_uri_for(port)):
        return cached

    client_id = register_oauth_client(supabase_url, [redirect_uri_for(p) for p in CALLBACK_PORTS])
    cache[supabase_url] = client_id
    with contextlib.suppress(OSError):
        (settings.ensure_config_dir() / CLIENT_CACHE_FILE).write_text(json.dumps(cache, indent=2))
    return client_id


def _client_accepts(supabase_url: str, client_id: str, redirect_uri: str) -> bool:
    """Ask the authorize endpoint whether the client still exists and allows this redirect.

    An unsupported response_type makes a valid request redirect back with an error before
    anything is stored, while an unknown client or redirect is answered with a 400.
    """
    query = urllib.parse.urlencode(
        {"client_id": client_id, "redirect_uri": redirect_uri, "response_type": "probe"}
    )
    try:
        response = httpx.get(
            f"{supabase_url}/auth/v1/oauth/authorize?{query}",
            follow_redirects=False,
            timeout=15.0,
        )
    except httpx.HTTPError:
        return False
    return response.is_redirect and response.headers.get("location", "").startswith(redirect_uri)


def _load_cache(settings: Settings) -> dict[str, str]:
    path = settings.config_dir / CLIENT_CACHE_FILE
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}
