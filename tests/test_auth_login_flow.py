"""End-to-end `minitest auth login` against a fake Supabase OAuth server, run as a real process."""

import base64
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest

CLI = "import sys; from minitest_cli.main import app; sys.argv[0] = 'minitest'; app()"
ACCESS_TOKEN = "header.eyJzdWIiOiJ1aWQtMSIsImVtYWlsIjoiYm90QGV4YW1wbGUuY29tIn0.sig"


class FakeAuthServer:
    """Enough of Supabase's OAuth 2.1 server: DCR, exact redirect matching, PKCE exchange."""

    def __init__(self) -> None:
        self.clients: dict[str, list[str]] = {}
        self.registrations = 0
        self.codes: dict[str, tuple[str, str]] = {}
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                url = urllib.parse.urlparse(self.path)
                params = dict(urllib.parse.parse_qsl(url.query))
                redirect_uri = params.get("redirect_uri", "")
                if redirect_uri not in fake.clients.get(params.get("client_id", ""), []):
                    self._send(400, {"msg": "invalid client_id or redirect_uri"})
                    return
                if params.get("response_type") != "code":
                    self._redirect(f"{redirect_uri}?error=invalid_request")
                    return
                code = uuid.uuid4().hex
                fake.codes[code] = (params["code_challenge"], params["client_id"])
                self._redirect(f"{redirect_uri}?code={code}")

            def do_POST(self) -> None:  # noqa: N802
                body = self.rfile.read(int(self.headers["Content-Length"])).decode()
                if self.path == "/auth/v1/oauth/clients/register":
                    client_id = str(uuid.uuid4())
                    fake.clients[client_id] = json.loads(body)["redirect_uris"]
                    fake.registrations += 1
                    self._send(201, {"client_id": client_id})
                    return
                form = dict(urllib.parse.parse_qsl(body))
                challenge, client_id = fake.codes.pop(form["code"])
                digest = hashlib.sha256(form["code_verifier"].encode()).digest()
                if base64.urlsafe_b64encode(digest).rstrip(b"=").decode() != challenge:
                    self._send(400, {"error": "invalid_grant"})
                    return
                assert form["client_id"] == client_id
                self._send(
                    200,
                    {"access_token": ACCESS_TOKEN, "refresh_token": "r-1", "expires_in": 3600},
                )

            def _send(self, status: int, payload: dict) -> None:
                encoded = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def _redirect(self, location: str) -> None:
                self.send_response(302)
                self.send_header("Location", location)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, format: str, *args: object) -> None:  # noqa: A002
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()


@pytest.fixture
def auth_server():
    server = FakeAuthServer()
    yield server
    server.server.shutdown()


@pytest.fixture
def cli_env(tmp_path, auth_server):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    npx = bin_dir / "npx"
    npx.write_text(f"#!/bin/sh\ntouch {tmp_path / 'npx-called'}\n")
    npx.chmod(0o755)
    return {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "MINITEST_CONFIG_DIR": str(tmp_path / "config"),
        "MINITEST_SUPABASE_URL": auth_server.url,
        "MINITEST_SUPABASE_PUBLISHABLE_KEY": "test-key",
    }


def _start_login(env: dict[str, str], *args: str) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, "-c", CLI, "--json", "auth", "login", *args],
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _login_by_visiting_url(env: dict[str, str]) -> tuple[subprocess.Popen[str], list[dict]]:
    proc = _start_login(env, "--no-browser")
    assert proc.stdout is not None
    first = json.loads(proc.stdout.readline())
    httpx.get(first["authorize_url"], follow_redirects=True, timeout=10)
    rest, _ = proc.communicate(timeout=30)
    return proc, [first, json.loads(rest)]


class TestUnattendedLogin:
    def test_login_json_prints_url_then_result_without_prompting(
        self, tmp_path, cli_env, auth_server
    ):
        proc, lines = _login_by_visiting_url(cli_env)

        assert proc.returncode == 0
        assert lines[0]["authorize_url"].startswith(f"{auth_server.url}/auth/v1/oauth/authorize?")
        assert lines[1] == {"authenticated": True, "email": "bot@example.com", "user_id": "uid-1"}
        saved = json.loads(Path(cli_env["MINITEST_CONFIG_DIR"], "credentials.json").read_text())
        assert saved["refresh_token"] == "r-1"
        assert not (tmp_path / "npx-called").exists()

    def test_second_login_reuses_the_registered_client(self, cli_env, auth_server):
        _login_by_visiting_url(cli_env)
        proc, _ = _login_by_visiting_url(cli_env)

        assert proc.returncode == 0
        assert auth_server.registrations == 1

    def test_login_registers_again_when_saved_client_is_gone(self, cli_env, auth_server):
        _login_by_visiting_url(cli_env)
        auth_server.clients.clear()

        proc, _ = _login_by_visiting_url(cli_env)

        assert proc.returncode == 0
        assert auth_server.registrations == 2

    def test_login_times_out_after_the_given_seconds(self, cli_env):
        started = time.monotonic()
        proc = _start_login(cli_env, "--no-browser", "--timeout", "1")
        _, stderr = proc.communicate(timeout=30)

        assert proc.returncode == 2
        assert "timed out after 1 seconds" in stderr
        assert time.monotonic() - started < 10
