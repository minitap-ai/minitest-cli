"""A fake Conductor (PR checks, SSE included) + testing-service for `minitest pr` tests."""

import asyncio
import json
from collections.abc import AsyncIterator, Callable, Iterator
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
CHECK_ID = "cccccccc-0000-0000-0000-000000000001"
IOS_BUILD = "bbbbbbbb-0000-0000-0000-00000000000a"
ANDROID_BUILD = "bbbbbbbb-0000-0000-0000-00000000000b"
CONDUCTOR = "conductor.test"
REPORT_PATH = f"/t/minitap/apps/{APP_ID}/test/pr-checks/1482"
REPORT_URL = f"https://app.minitap.ai{REPORT_PATH}"
CREATE = "POST /api/v1/pr-checks"
EVENTS = f"GET /api/v1/pr-checks/{CHECK_ID}/events"
REPORT = f"GET /api/v1/pr-checks/{CHECK_ID}"
MARKDOWN = f"GET /api/v1/pr-checks/{CHECK_ID}/report.md"
FILES = f"POST /api/v1/pr-checks/{CHECK_ID}/files"
BY_PR = f"GET /api/v1/apps/{APP_ID}/pr-checks/1482"

Reply = httpx.Response | Callable[[httpx.Request], httpx.Response]

PLAN = [
    {"id": "c1", "group": "change", "label": "Favourite heart on each card", "expected": "A heart"},
    {"id": "c2", "group": "impact", "label": "Home still lists restaurants", "why": "Browse home"},
]


def created(push: int = 1, state: str = "queued") -> dict[str, Any]:
    return {
        "id": CHECK_ID,
        "draftId": "dddddddd-0000-0000-0000-000000000001",
        "sessionId": "ssssssss-0000-0000-0000-000000000001",
        "prNumber": 1482,
        "push": push,
        "state": state,
        "reportUrl": REPORT_PATH,
    }


def report(verdict: str | None, state: str = "done", push: int = 1, **extra: Any) -> dict[str, Any]:
    ios_verdict = {"not_ready": "critical", "ready_with_warnings": "warning"}.get(
        verdict or "", "passed"
    )
    checks = [
        {**PLAN[0], "platforms": {"ios": {"verdict": ios_verdict, "at": 72, "seen": "No heart"}}},
        {**PLAN[1], "platforms": {"ios": {"verdict": "passed", "at": 10}}},
    ]
    return {
        **created(push, state),
        "title": "Favourites",
        "verdict": verdict,
        "counts": {"ios": {"passed": 1, ios_verdict: 1}},
        "checks": checks if state != "queued" else [],
        "questions": [],
        **extra,
    }


def sse(*events: tuple[str, dict[str, Any]], start: int = 1) -> bytes:
    frames = [
        f"id: {n}\nevent: {kind}\ndata: {json.dumps(data)}\n\n"
        for n, (kind, data) in enumerate(events, start=start)
    ]
    return (": heartbeat\n\n" + "".join(frames)).encode()


def story(verdict: str, push: int = 1) -> bytes:
    """A full push on the stream: states, plan, both results and the verdict."""
    item = {"not_ready": "critical", "ready_with_warnings": "warning"}.get(verdict, "passed")
    return sse(
        ("pr_check.state", {"state": "preparing", "push": push}),
        ("pr_check.plan", {"checks": PLAN}),
        ("pr_check.state", {"state": "exploring", "push": push}),
        ("pr_check.item", {"checkId": "c1", "platform": "ios", "verdict": item, "at": 72}),
        ("pr_check.item", {"checkId": "c2", "platform": "ios", "verdict": "passed", "at": 10}),
        ("pr_check.verdict", {"push": push, "verdict": verdict, "counts": {}}),
    )


class Stream(httpx.AsyncByteStream):
    """An event stream that sends ``body``, then drops (``fail``) or hangs (``hang``)."""

    def __init__(self, body: bytes, *, fail: bool = False, hang: bool = False) -> None:
        self.body, self.fail, self.hang = body, fail, hang

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield self.body
        if self.hang:
            await asyncio.sleep(3600)
        if self.fail:
            raise httpx.ReadError("connection reset")


def stream(body: bytes, **kwargs: bool) -> Callable[[httpx.Request], httpx.Response]:
    """A fresh event stream for every request, so a reconnect gets one too."""
    return lambda _request: httpx.Response(
        200, headers={"content-type": "text/event-stream"}, stream=Stream(body, **kwargs)
    )


@dataclass
class Backend:
    """Replies keyed by "METHOD /path", popped in order; the last one sticks."""

    routes: dict[str, list[Reply]] = field(default_factory=dict)
    requests: list[httpx.Request] = field(default_factory=list)

    def on(self, route: str, *replies: Reply) -> "Backend":
        self.routes[route] = list(replies)
        return self

    def sent(self, route: str) -> list[httpx.Request]:
        return [r for r in self.requests if f"{r.method} {r.url.path}" == route]

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        route = f"{request.method} {request.url.path}"
        if request.url.host != CONDUCTOR:
            if route == "GET /api/v1/apps":
                apps = [{"id": APP_ID, "name": "Food", "tenantId": TENANT_ID}]
                return httpx.Response(200, json={"apps": apps})
            if route == f"POST /api/v1/apps/{APP_ID}/build":
                build = {"id": IOS_BUILD, "appId": APP_ID, "createdAt": "2026-11-26T00:00:00Z"}
                return httpx.Response(201, json=build)
        else:
            assert request.url.params.get("tenantId") == TENANT_ID
        replies = self.routes.get(route)
        if not replies:
            return httpx.Response(404, json={"detail": f"no {route} in the fake"})
        reply = replies.pop(0) if len(replies) > 1 else replies[0]
        return reply(request) if callable(reply) else reply


def happy(verdict: str = "ready") -> Backend:
    return (
        Backend()
        .on(CREATE, httpx.Response(201, json=created()))
        .on(EVENTS, stream(story(verdict)))
        .on(REPORT, httpx.Response(200, json=report(verdict)))
        .on(MARKDOWN, httpx.Response(200, text=f"## Verdict: {verdict}\n\n{REPORT_URL}\n"))
    )


@contextmanager
def wired(backend: Backend) -> Iterator[None]:
    async_client = httpx.AsyncClient
    transport = httpx.MockTransport(backend.handle)
    settings = Settings(token="test-token", app_id=APP_ID, conductor_url=f"https://{CONDUCTOR}")
    with (
        patch("minitest_cli.main.get_settings", return_value=settings),
        patch("minitest_cli.main.check_for_updates"),
        patch(
            "minitest_cli.api.client.httpx.AsyncClient",
            side_effect=lambda **kwargs: async_client(**kwargs, transport=transport),
        ),
        patch("minitest_cli.commands.pr_follow.POLL_SECONDS", 0),
    ):
        yield


def invoke(backend: Backend, args: list[str], *, stdin: str | None = None):
    with wired(backend):
        return CliRunner().invoke(app, args, input=stdin)
