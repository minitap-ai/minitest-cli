"""`--app` / MINITEST_APP_ID take an app id or an app name, for every command."""

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import patch

import httpx
import pytest
import typer

from minitest_cli.core.app_context import resolve_app_id
from minitest_cli.core.config import Settings

CLUTCH = "4a946bbd-1732-42ac-a572-25003659bed5"
APPS = [
    {"id": CLUTCH, "name": "Clutch", "tenantId": "t-1"},
    {"id": "9f4bd175-c0ce-4e3c-b911-44e9dcfd9e14", "name": "Debatium Couple", "tenantId": "t-1"},
    {"id": "11111111-0000-0000-0000-000000000001", "name": "Twin", "tenantId": "t-1"},
    {"id": "11111111-0000-0000-0000-000000000002", "name": "twin", "tenantId": "t-1"},
]

pytestmark = pytest.mark.real_app_lookup


@contextmanager
def _apps(reply: httpx.Response) -> Iterator[list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return reply

    async_client = httpx.AsyncClient
    with patch(
        "minitest_cli.api.client.httpx.AsyncClient",
        side_effect=lambda **kw: async_client(**kw, transport=httpx.MockTransport(handle)),
    ):
        yield seen


def _settings(**overrides) -> Settings:
    return Settings(token="t", **overrides)


class TestResolveAppId:
    def test_resolve_uuid_is_used_as_is_without_a_lookup(self):
        with _apps(httpx.Response(500)) as seen:
            assert resolve_app_id(_settings(), CLUTCH) == CLUTCH
        assert seen == []

    def test_resolve_name_is_case_insensitive(self):
        with _apps(httpx.Response(200, json={"apps": APPS})):
            assert resolve_app_id(_settings(), "clutch") == CLUTCH

    def test_resolve_name_with_spaces_from_env(self):
        with _apps(httpx.Response(200, json={"apps": APPS})):
            app_id = resolve_app_id(_settings(app_id="Debatium Couple"))
        assert app_id == "9f4bd175-c0ce-4e3c-b911-44e9dcfd9e14"

    def test_resolve_unknown_name_exits_not_found(self):
        with _apps(httpx.Response(200, json={"apps": APPS})), pytest.raises(typer.Exit) as exc:
            resolve_app_id(_settings(), "Nope")
        assert exc.value.exit_code == 4

    def test_resolve_ambiguous_name_exits_general_error(self):
        with _apps(httpx.Response(200, json={"apps": APPS})), pytest.raises(typer.Exit) as exc:
            resolve_app_id(_settings(), "Twin")
        assert exc.value.exit_code == 1

    def test_resolve_rejected_key_exits_auth_failure(self):
        with (
            _apps(httpx.Response(401, json={"detail": "bad key"})),
            pytest.raises(typer.Exit) as exc,
        ):
            resolve_app_id(_settings(), "Clutch")
        assert exc.value.exit_code == 1

    def test_resolve_name_inside_a_running_event_loop(self):
        async def inside() -> str:
            return resolve_app_id(_settings(), "Clutch")

        with _apps(httpx.Response(200, json={"apps": APPS})):
            assert asyncio.run(inside()) == CLUTCH
