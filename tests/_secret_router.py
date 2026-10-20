"""Route mocked testing-service calls for the ``secret`` command tests."""

import json
from typing import Any

import httpx
from typer.testing import CliRunner

from tests._commit_transport import cli_context, make_settings, routed

APP = "a0d9820f-5136-4f70-b46b-e5966f56bfb5"
SECRETS = f"/api/v1/apps/{APP}/secrets"
STORIES = f"/api/v1/apps/{APP}/user-stories"
PROFILES = f"/api/v1/apps/{APP}/test-profiles"
FAKE = "fake-hunter22"

runner = CliRunner()


class Router:
    def __init__(self, routes: dict[tuple[str, str], httpx.Response]) -> None:
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = (request.method, request.url.path)
        if key in self.routes:
            return self.routes[key]
        return httpx.Response(404, json={"detail": "Not Found"})

    def body(self, method: str, path: str) -> Any:
        sent = [r for r in self.requests if r.method == method and r.url.path == path]
        return json.loads(sent[-1].content)

    def called(self, method: str) -> list[str]:
        return [r.url.path for r in self.requests if r.method == method]


def invoke(app, args, router, tmp_path, *, json_mode=False, stdin=None, env=None):
    with routed(router), cli_context(make_settings(tmp_path), json_mode=json_mode):
        return runner.invoke(app, args, input=stdin, env=env)


def vault(secrets=None, requests=None) -> httpx.Response:
    return httpx.Response(200, json={"secrets": secrets or [], "requests": requests or []})


def secret_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "name": "ADMIN_PASSWORD",
        "kind": "password",
        "note": "Admin login",
        "version": 2,
        "updatedAt": "2026-10-20T10:00:00Z",
        "updatedBy": "jp@minitap.ai",
        "usages": [{"type": "persona", "id": "p1", "name": "Admin", "field": "password"}],
    }
    return {**row, **overrides}
