"""A fake testing-service + Conductor pair for `minitest draft` tests, wired through httpx."""

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
TENANT_ID = "tttttttt-0000-0000-0000-000000000001"
DRAFT_ID = "dddddddd-0000-0000-0000-000000000001"
ASK_ID = "eeeeeeee-0000-0000-0000-000000000001"
CONDUCTOR_HOST = "conductor.test"

Reply = httpx.Response | Callable[[httpx.Request], httpx.Response]


def draft(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": DRAFT_ID,
        "appId": APP_ID,
        "sessionId": "ssssssss-0000-0000-0000-000000000001",
        "title": "Checkout",
        "state": "drafting",
        "stateReason": "Mini will write the change next",
        "stateReasonCode": "queued",
        "miniWriting": False,
        "needsUser": False,
        "autoCheck": False,
        "autoMerge": False,
        "asks": [],
    }
    return body | overrides


@dataclass
class Backend:
    """Conductor replies keyed by "METHOD /path", popped in order; the last one sticks."""

    routes: dict[str, list[Reply]] = field(default_factory=dict)
    requests: list[httpx.Request] = field(default_factory=list)

    def on(self, method: str, path: str, *replies: Reply) -> "Backend":
        self.routes[f"{method} {path}"] = list(replies)
        return self

    def sent(self, method: str, path: str) -> list[dict[str, Any] | None]:
        return [
            json.loads(r.content) if r.content else None
            for r in self.requests
            if r.method == method and r.url.path == path and r.url.host == CONDUCTOR_HOST
        ]

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.host != CONDUCTOR_HOST:
            apps = [{"id": APP_ID, "name": "Shop", "tenantId": TENANT_ID}]
            return httpx.Response(200, json={"apps": apps})
        self.requests.append(request)
        assert request.url.params.get("tenantId") == TENANT_ID
        replies = self.routes.get(f"{request.method} {request.url.path}")
        if not replies:
            return httpx.Response(404, json={"detail": "no such route in the fake"})
        reply = replies.pop(0) if len(replies) > 1 else replies[0]
        return reply(request) if callable(reply) else reply


@contextmanager
def _wired(backend: Backend) -> Iterator[None]:
    async_client = httpx.AsyncClient
    transport = httpx.MockTransport(backend.handle)
    settings = Settings(
        token="test-token", app_id=APP_ID, conductor_url=f"https://{CONDUCTOR_HOST}"
    )
    with (
        patch("minitest_cli.main.get_settings", return_value=settings),
        patch("minitest_cli.main.check_for_updates"),
        patch(
            "minitest_cli.api.client.httpx.AsyncClient",
            side_effect=lambda **kwargs: async_client(**kwargs, transport=transport),
        ),
        patch("minitest_cli.commands.draft_helpers.RETRY_DELAY_SECONDS", 0),
    ):
        yield


def invoke(backend: Backend, args: list[str], *, stdin: str | None = None):
    with _wired(backend):
        return CliRunner().invoke(app, args, input=stdin)
