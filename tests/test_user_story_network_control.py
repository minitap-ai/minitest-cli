"""scenario network-control."""

import json
from contextlib import contextmanager
from unittest.mock import patch

import httpx
import typer
from typer.testing import CliRunner

from minitest_cli.commands.user_story import app as user_story_app
from minitest_cli.core.config import Settings

runner = CliRunner()
STORY = {
    "acceptanceCriteria": [
        {"criterionId": "crit-1", "content": "The feed loads"},
        {"criterionId": "crit-2", "content": "Offline, the card shows Offline mode"},
    ]
}


def _settings(tmp_path) -> Settings:
    return Settings(
        config_dir=tmp_path,
        token="test-token",
        app_id="app-123",
        supabase_url="https://test.supabase.co",
        supabase_publishable_key="test-publishable-key",
    )


@contextmanager
def _server():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json=STORY)
        return httpx.Response(204)

    async_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    with patch(
        "minitest_cli.api.client.httpx.AsyncClient",
        side_effect=lambda **kwargs: async_client(**kwargs, transport=transport),
    ):
        yield requests


def _invoke(args: list[str], settings: Settings):
    with (
        patch.object(typer.Context, "settings", settings, create=True),
        patch.object(typer.Context, "json_mode", False, create=True),
        patch.object(typer.Context, "app_flag", None, create=True),
    ):
        return runner.invoke(user_story_app, args)


def _puts(requests: list[httpx.Request]) -> list[tuple[str, dict]]:
    return [(r.url.path, json.loads(r.content)) for r in requests if r.method == "PUT"]


class TestNetworkControl:
    def test_an_index_marks_that_criterion_of_the_live_scenario(self, tmp_path) -> None:
        with _server() as requests:
            result = _invoke(["network-control", "story-1", "2"], _settings(tmp_path))

        assert result.exit_code == 0, result.output
        assert _puts(requests) == [
            (
                "/api/v1/apps/app-123/criteria/crit-2/network-control",
                {"needsNetworkControl": True},
            )
        ]

    def test_a_draft_criterion_id_is_cleared_without_reading_the_scenario(self, tmp_path) -> None:
        with _server() as requests:
            result = _invoke(
                ["network-control", "story-1", "draft-crit", "--off"], _settings(tmp_path)
            )

        assert result.exit_code == 0, result.output
        assert [r.method for r in requests] == ["PUT"]
        assert _puts(requests) == [
            (
                "/api/v1/apps/app-123/criteria/draft-crit/network-control",
                {"needsNetworkControl": False},
            )
        ]

    def test_an_index_out_of_range_changes_nothing(self, tmp_path) -> None:
        with _server() as requests:
            result = _invoke(["network-control", "story-1", "3"], _settings(tmp_path))

        assert result.exit_code == 1
        assert _puts(requests) == []
