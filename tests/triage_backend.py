"""A fake testing-service + Conductor for `run ask` and `issues` triage tests, wired via httpx."""

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

import httpx
from typer.testing import CliRunner

from minitest_cli.core.config import Settings
from minitest_cli.main import app

APP_ID = "aaaaaaaa-0000-0000-0000-000000000001"
BATCH_ID = "bbbbbbbb-0000-0000-0000-000000000001"
ASK_ID = "eeeeeeee-0000-0000-0000-000000000001"
ISSUE_ID = "11111111-0000-0000-0000-000000000001"
RESULT_ID = "22222222-0000-0000-0000-000000000001"
CRITERION_ID = "33333333-0000-0000-0000-000000000001"
TAG_ID = "44444444-0000-0000-0000-000000000001"
API_HOST = "api.test"
CONDUCTOR_HOST = "conductor.test"
APP_PATH = f"/api/v1/apps/{APP_ID}"

Reply = httpx.Response | Callable[[httpx.Request], httpx.Response]


def failure(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": ISSUE_ID,
        "status": "open",
        "issueStatus": "review",
        "criticality": "critical",
        "criterionId": CRITERION_ID,
        "acceptanceCriteriaResultId": RESULT_ID,
        "feedbackPending": False,
    }
    return body | overrides


@dataclass
class Backend:
    """Replies keyed by "METHOD host/path", popped in order; the last one sticks."""

    routes: dict[str, list[Reply]] = field(default_factory=dict)
    requests: list[httpx.Request] = field(default_factory=list)

    def on(self, method: str, path: str, *replies: Reply, host: str = API_HOST) -> "Backend":
        self.routes[f"{method} {host}{path}"] = list(replies)
        return self

    def conductor(self, method: str, path: str, *replies: Reply) -> "Backend":
        return self.on(method, path, *replies, host=CONDUCTOR_HOST)

    def sent(self, method: str, path: str) -> list[Any]:
        return [
            json.loads(r.content) if r.content else None
            for r in self.requests
            if r.method == method and r.url.path == path
        ]

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        replies = self.routes.get(f"{request.method} {request.url.host}{request.url.path}")
        if not replies:
            return httpx.Response(404, json={"detail": "no such route in the fake"})
        reply = replies.pop(0) if len(replies) > 1 else replies[0]
        return reply(request) if callable(reply) else reply


@contextmanager
def _wired(backend: Backend) -> Iterator[None]:
    async_client = httpx.AsyncClient
    transport = httpx.MockTransport(backend.handle)
    settings = Settings(
        token="test-token",
        app_id=APP_ID,
        api_url=f"https://{API_HOST}",
        conductor_url=f"https://{CONDUCTOR_HOST}",
    )
    with (
        patch("minitest_cli.main.get_settings", return_value=settings),
        patch("minitest_cli.main.check_for_updates"),
        patch(
            "minitest_cli.api.client.httpx.AsyncClient",
            side_effect=lambda **kwargs: async_client(**kwargs, transport=transport),
        ),
        patch("minitest_cli.commands.issues_not_a_bug.POLL_INTERVAL_SECONDS", 0),
    ):
        yield


def invoke(backend: Backend, args: list[str], *, stdin: str | None = None):
    with _wired(backend):
        return CliRunner().invoke(app, args, input=stdin)
