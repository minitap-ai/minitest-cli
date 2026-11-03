"""ApiClient never replays cookies: the load balancer's affinity cookie would pin it to one pod."""

import asyncio

import httpx
import pytest

from minitest_cli.api.client import ApiClient
from minitest_cli.core.config import Settings

AFFINITY = "GCLB=CL3x-affinity; Path=/; HttpOnly; Expires=Thu, 05 Nov 2026 00:00:00 GMT"


@pytest.fixture
def backend(monkeypatch):
    """Every response sets an affinity cookie; `/redirect` bounces to `/final`."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        headers = {"Set-Cookie": AFFINITY}
        if request.url.path == "/redirect":
            return httpx.Response(302, headers={**headers, "Location": "/final"})
        return httpx.Response(200, headers=headers, json={})

    async_client = httpx.AsyncClient
    monkeypatch.setattr(
        "minitest_cli.api.client.httpx.AsyncClient",
        lambda **kwargs: async_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    return Settings(token="test-token", api_url="https://api.test"), requests


def _cookie_headers(requests: list[httpx.Request]) -> list[str | None]:
    return [r.headers.get("Cookie") for r in requests]


class TestNoCookies:
    def test_get_after_set_cookie_sends_no_cookie(self, backend) -> None:
        settings, requests = backend

        async def calls() -> int:
            async with ApiClient(settings) as client:
                for _ in range(3):
                    await client.get("/api/v1/apps")
                return len(client._ensure_client().cookies)

        assert asyncio.run(calls()) == 0
        assert len(requests) == 3
        assert _cookie_headers(requests) == [None, None, None]
        assert all(r.headers["Authorization"] == "Bearer test-token" for r in requests)

    def test_redirect_hop_sends_no_cookie(self, backend) -> None:
        settings, requests = backend

        async def calls() -> int:
            async with ApiClient(settings) as client:
                resp = await client.get("/redirect", follow_redirects=True)
                await client.post("/api/v1/apps", json={})
                return resp.status_code

        assert asyncio.run(calls()) == 200
        assert [r.url.path for r in requests] == ["/redirect", "/final", "/api/v1/apps"]
        assert _cookie_headers(requests) == [None, None, None]

    def test_upload_after_set_cookie_sends_no_cookie(self, backend) -> None:
        settings, requests = backend

        async def calls() -> None:
            async with ApiClient(settings) as client:
                await client.get("/api/v1/apps")
                await client.upload_file(
                    "/api/v1/apps/app-1/builds",
                    files={"file": ("app.apk", b"bytes", "application/octet-stream")},
                )

        asyncio.run(calls())
        assert requests[1].headers["Content-Type"].startswith("multipart/form-data")
        assert _cookie_headers(requests) == [None, None]

    def test_explicit_cookie_set_is_dropped(self, backend) -> None:
        settings, requests = backend

        async def calls() -> None:
            async with ApiClient(settings) as client:
                client._ensure_client().cookies.set("GCLB", "pinned")
                await client.get("/api/v1/apps")

        asyncio.run(calls())
        assert _cookie_headers(requests) == [None]
