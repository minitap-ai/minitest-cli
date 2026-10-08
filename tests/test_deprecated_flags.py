"""Renamed flags keep a hidden alias: same requests, same JSON, one warning."""

import json
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from click import unstyle
from typer.testing import CliRunner

from minitest_cli.core.config import Settings
from minitest_cli.main import app

runner = CliRunner()

APP = "app-123"
SHA = "2c589b1b370be5397f6d8774940c989e9110a625"
SCENARIO = "8a0d1c2e-9f5c-4c34-b1b6-2b9fd0f6f8a1"
BATCH = {
    "id": "2e20026b-04c4-4a5f-b6f0-aa4b5207e3e3",
    "appId": APP,
    "tenantId": "92a7a284-7c32-41f4-bb79-2e1a95c69c5a",
    "source": "cli",
    "status": "pending",
    "commitSha": SHA,
    "createdAt": "2026-08-31T10:00:00Z",
    "targets": [],
    "storyRuns": [],
}
BATCH_PAGE = {"items": [], "total": 0, "page": 1, "pageSize": 20}
RUN_ID = "11111111-2222-3333-4444-555555555555"
TARGET = "aaaaaaaa-0000-0000-0000-000000000001"


def _story_run(cancelled: bool) -> dict[str, Any]:
    platform = {
        "platform": "ios",
        "srpId": TARGET,
        "executionState": "running",
        "cancellationRequestedAt": "2026-10-05T10:01:00Z" if cancelled else None,
    }
    return {
        "id": RUN_ID,
        "userStoryId": SCENARIO,
        "createdAt": "2026-10-05T10:00:00Z",
        "platforms": [platform],
    }


def _respond(request: httpx.Request) -> httpx.Response:
    if request.url.path == f"/api/v1/apps/{APP}/batches":
        return httpx.Response(200, json=BATCH if request.method == "POST" else BATCH_PAGE)
    if request.url.path == f"/api/v1/apps/{APP}/story-runs/{RUN_ID}":
        return httpx.Response(200, json=_story_run(cancelled=False))
    if request.url.path == f"/api/v1/apps/{APP}/story-run-platforms/{TARGET}/cancel":
        return httpx.Response(200, json=_story_run(cancelled=True))
    return httpx.Response(404, json={"detail": f"unexpected {request.url.path}"})


def _invoke(args: list[str]) -> tuple[Any, list[tuple[str, str, bytes]]]:
    sent: list[tuple[str, str, bytes]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append((request.method, str(request.url), request.content))
        return _respond(request)

    async_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    settings = Settings(token="test-token", app_id=APP)
    with (
        patch("minitest_cli.main.get_settings", return_value=settings),
        patch("minitest_cli.main.check_for_updates"),
        patch(
            "minitest_cli.api.client.httpx.AsyncClient",
            side_effect=lambda **kwargs: async_client(**kwargs, transport=transport),
        ),
    ):
        return runner.invoke(app, ["--json", *args]), sent


@pytest.mark.parametrize(
    ("command", "new", "old", "value"),
    [
        (["run", "from-commit", SHA, "--no-watch"], "--scenario", "--user-story", SCENARIO),
        (["run", "from-commit", SHA, "--no-watch"], "--scenario", "-u", SCENARIO),
        (["batch", "list"], "--scenario", "--user-story-id", SCENARIO),
        (["run", "cancel", RUN_ID], "--target-id", "--srp", TARGET),
    ],
)
def test_deprecated_flag_behaves_like_its_new_name_and_warns(command, new, old, value):
    current, current_requests = _invoke([*command, new, value])
    legacy, legacy_requests = _invoke([*command, old, value])

    assert current.exit_code == legacy.exit_code == 0, legacy.output
    assert legacy_requests == current_requests
    assert value in str(current_requests)
    assert legacy.stdout == current.stdout
    json.loads(legacy.stdout)
    warning = " ".join(unstyle(legacy.stderr).split())
    assert warning.count(f"is deprecated; use {new} instead.") == 1
    assert "deprecated" not in current.stderr
