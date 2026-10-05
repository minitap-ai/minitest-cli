"""Long-lived clients must use refreshed OAuth credentials before sending."""

import asyncio
from unittest.mock import Mock

import httpx
import pytest
from pydantic import SecretStr

from minitest_cli.api.client import ApiClient
from minitest_cli.core.auth import Credentials, SessionRevokedError, save_credentials
from minitest_cli.core.config import Settings


@pytest.fixture
def owned_auth(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings(
        config_dir=tmp_path,
        token=None,
        api_key=None,
        api_url="https://owned.invalid",
        channel="cli",
        conversation_id="owned-conversation",
        cause="owned-cause",
    )
    clock = [1000.0]
    original = Credentials(
        access_token="owned-initial",
        refresh_token="owned-refresh",
        expires_at=1600,
        user_id="owned-user",
        email="owned@example.invalid",
    )
    save_credentials(settings, original)
    monkeypatch.setattr("minitest_cli.core.credentials.time.time", lambda: clock[0])

    def renew(current_settings, previous):
        updated = previous.model_copy(update={"access_token": "owned-renewed", "expires_at": 5300})
        save_credentials(current_settings, updated)
        return updated

    refresh = Mock(side_effect=renew)
    monkeypatch.setattr("minitest_cli.core.auth.refresh_token", refresh)
    requests = []
    real_client = httpx.AsyncClient

    def respond(request):
        requests.append(request)
        accepted = {"Bearer owned-renewed"}
        if clock[0] < 1600:
            accepted.add("Bearer owned-initial")
        status = 200 if request.headers["Authorization"] in accepted else 401
        return httpx.Response(status)

    monkeypatch.setattr(
        "minitest_cli.api.client.httpx.AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs),
    )
    return settings, clock, refresh, requests


async def _send(client, method):
    if method == "upload_file":
        return await client.upload_file("/owned", files={"file": ("owned.txt", b"content")})
    if method == "request":
        return await client.request("GET", "/owned")
    return await getattr(client, method)("/owned")


class TestApiClientAuth:
    @pytest.mark.parametrize(
        "method", ["get", "post", "put", "patch", "delete", "request", "upload_file"]
    )
    @pytest.mark.parametrize("refresh_time", [1300, 1700])
    def test_existing_client_refreshes_before_sending(self, owned_auth, method, refresh_time):
        settings, clock, refresh, requests = owned_auth

        async def scenario():
            async with ApiClient(settings) as client:
                assert (await _send(client, method)).status_code == 200
                clock[0] = refresh_time
                assert (await _send(client, method)).status_code == 200
                async with ApiClient(settings) as fresh:
                    assert (await fresh.get("/owned")).status_code == 200
                assert (await client.get("/owned")).status_code == 200

        asyncio.run(scenario())
        refresh.assert_called_once()
        assert len(requests) == 4
        assert requests[1].headers["Authorization"] == "Bearer owned-renewed"
        assert requests[1].headers["X-Minitest-Channel"] == "cli"
        assert requests[1].headers["X-Minitest-Conversation-Id"] == "owned-conversation"
        assert requests[1].headers["X-Minitest-Cause"] == "owned-cause"

    @pytest.mark.parametrize("source", ["override", "token", "api_key"])
    def test_explicit_auth_keeps_precedence_without_oauth_refresh(self, owned_auth, source):
        settings, clock, refresh, requests = owned_auth
        override = "owned-explicit" if source == "override" else None
        if source == "token":
            settings.token = "owned-explicit"
        if source == "api_key":
            settings.api_key = SecretStr("owned-explicit")

        async def scenario():
            async with ApiClient(settings, token_override=override) as client:
                clock[0] = 1700
                await client.get("/owned")
                await client.get("/owned")

        asyncio.run(scenario())
        refresh.assert_not_called()
        assert all(r.headers["Authorization"] == "Bearer owned-explicit" for r in requests)

    def test_revoked_refresh_prevents_request(self, owned_auth):
        settings, clock, refresh, requests = owned_auth
        refresh.side_effect = SessionRevokedError("owned revoked session")

        async def scenario():
            async with ApiClient(settings) as client:
                clock[0] = 1700
                with pytest.raises(SystemExit) as error:
                    await client.post("/owned")
                assert error.value.code == 2

        asyncio.run(scenario())
        assert requests == []
        refresh.assert_called_once()
        assert not (settings.config_dir / "credentials.json").exists()

    def test_unauthorized_write_is_not_replayed(self, owned_auth):
        settings, _, refresh, requests = owned_auth

        async def scenario():
            async with ApiClient(settings, token_override="owned-rejected") as client:
                assert (await client.post("/owned")).status_code == 401

        asyncio.run(scenario())
        assert len(requests) == 1
        refresh.assert_not_called()
