"""A long-lived ApiClient must keep authenticating after its OAuth access token expires."""

import asyncio
from unittest.mock import Mock

import httpx
import pytest

from minitest_cli.api.client import ApiClient
from minitest_cli.core.auth import Credentials, SessionRevokedError, save_credentials
from minitest_cli.core.config import Settings

EXPIRES_AT = 1600.0


@pytest.fixture
def oauth_session(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings(config_dir=tmp_path, token=None, api_key=None, api_url="https://api.test")
    save_credentials(
        settings,
        Credentials(
            access_token="initial",
            refresh_token="refresh",
            expires_at=EXPIRES_AT,
            user_id="user",
            email="user@example.test",
        ),
    )
    clock = [1000.0]
    monkeypatch.setattr("minitest_cli.core.credentials.time.time", lambda: clock[0])

    def renew(current_settings, previous):
        renewed = previous.model_copy(update={"access_token": "renewed", "expires_at": 5000})
        save_credentials(current_settings, renewed)
        return renewed

    refresh = Mock(side_effect=renew)
    monkeypatch.setattr("minitest_cli.core.auth.refresh_token", refresh)

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        valid = {"Bearer renewed"} | ({"Bearer initial"} if clock[0] < EXPIRES_AT else set())
        return httpx.Response(200 if request.headers["Authorization"] in valid else 401)

    async_client = httpx.AsyncClient
    monkeypatch.setattr(
        "minitest_cli.api.client.httpx.AsyncClient",
        lambda **kwargs: async_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    return settings, clock, refresh, requests


@pytest.mark.parametrize("later", [EXPIRES_AT - 300, EXPIRES_AT + 100])
def test_open_client_refreshes_token_once_it_nears_expiry(oauth_session, later):
    settings, clock, refresh, requests = oauth_session

    async def poll() -> list[int]:
        async with ApiClient(settings) as client:
            first = await client.get("/runs/1")
            clock[0] = later
            second = await client.get("/runs/1")
            third = await client.get("/runs/1")
            return [first.status_code, second.status_code, third.status_code]

    assert asyncio.run(poll()) == [200, 200, 200]
    assert [r.headers["Authorization"] for r in requests] == [
        "Bearer initial",
        "Bearer renewed",
        "Bearer renewed",
    ]
    assert refresh.call_count == 1


def test_token_override_is_never_replaced_by_oauth(oauth_session):
    settings, clock, refresh, requests = oauth_session

    async def poll() -> None:
        async with ApiClient(settings, token_override="explicit") as client:
            clock[0] = EXPIRES_AT + 100
            await client.get("/runs/1")

    asyncio.run(poll())
    assert requests[0].headers["Authorization"] == "Bearer explicit"
    refresh.assert_not_called()


def test_revoked_session_exits_before_sending(oauth_session):
    settings, clock, refresh, requests = oauth_session
    refresh.side_effect = SessionRevokedError

    async def poll() -> None:
        async with ApiClient(settings) as client:
            clock[0] = EXPIRES_AT + 100
            await client.get("/runs/1")

    with pytest.raises(SystemExit) as exit_info:
        asyncio.run(poll())
    assert exit_info.value.code == 2
    assert requests == []
    assert not (settings.config_dir / "credentials.json").exists()
