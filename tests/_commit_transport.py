"""Real httpx request cycles for the commit-driven commands, no client mocks."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import typer

from minitest_cli.core.config import Settings

Handler = Callable[[httpx.Request], httpx.Response]


def make_settings(tmp_path: Path, **overrides: Any) -> Settings:
    defaults: dict[str, Any] = {
        "config_dir": tmp_path,
        "token": "test-token",
        "supabase_url": "https://test.supabase.co",
        "supabase_publishable_key": "test-key",
        "app_id": "a0d9820f-5136-4f70-b46b-e5966f56bfb5",
        "api_url": "https://testing.example",
        "apps_manager_url": "https://apps.example",
    }
    defaults.update(overrides)
    return Settings(**defaults)


@contextmanager
def routed(handler: Handler) -> Iterator[None]:
    real = httpx.AsyncClient

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(**kwargs)

    with patch("httpx.AsyncClient", factory):
        yield


@contextmanager
def cli_context(settings: Settings, *, json_mode: bool = True) -> Iterator[None]:
    patches = [
        patch.object(typer.Context, "settings", settings, create=True),
        patch.object(typer.Context, "json_mode", json_mode, create=True),
        patch.object(typer.Context, "app_flag", None, create=True),
    ]
    for item in patches:
        item.start()
    try:
        yield
    finally:
        for item in patches:
            item.stop()


def apps_list_response(settings: Settings) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "apps": [
                {
                    "id": settings.app_id,
                    "name": "Mini-skills Web",
                    "tenantId": "92a7a284-7c32-41f4-bb79-2e1a95c69c5a",
                }
            ]
        },
    )
