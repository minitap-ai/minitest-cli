"""user-story allow-setup-commit / revoke-setup-commit."""

import json
from contextlib import contextmanager
from unittest.mock import patch

import httpx
import typer
from typer.testing import CliRunner

from minitest_cli.commands.user_story import app as user_story_app
from minitest_cli.core.config import Settings

runner = CliRunner()
PATH = "/api/v1/apps/app-123/user-stories/story-1/setup-commit-permission"
QUOTE = "Yes, zero-value flexible bookings with the Stripe test card are fine."


def _settings(tmp_path) -> Settings:
    return Settings(
        config_dir=tmp_path,
        token="test-token",
        app_id="app-123",
        supabase_url="https://test.supabase.co",
        supabase_publishable_key="test-publishable-key",
        conversation_id="ses_42",
    )


@contextmanager
def _server(status: int, body: dict | None = None):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status, json=body) if body is not None else httpx.Response(status)

    async_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    with patch(
        "minitest_cli.api.client.httpx.AsyncClient",
        side_effect=lambda **kwargs: async_client(**kwargs, transport=transport),
    ):
        yield requests


def _invoke(args: list[str], settings: Settings, *, json_mode: bool = False):
    with (
        patch.object(typer.Context, "settings", settings, create=True),
        patch.object(typer.Context, "json_mode", json_mode, create=True),
        patch.object(typer.Context, "app_flag", None, create=True),
    ):
        return runner.invoke(user_story_app, args)


class TestAllowSetupCommit:
    def test_sends_the_trimmed_quote_from_the_conversation(self, tmp_path) -> None:
        with _server(200, {"userStoryId": "story-1", "customerQuote": QUOTE}) as requests:
            result = _invoke(
                ["allow-setup-commit", "story-1", "--customer-quote", f"  {QUOTE} "],
                _settings(tmp_path),
                json_mode=True,
            )

        assert result.exit_code == 0, result.output
        [request] = requests
        assert request.method == "PUT"
        assert request.url.path == PATH
        assert json.loads(request.content) == {"customerQuote": QUOTE}
        assert request.headers["X-Minitest-Conversation-Id"] == "ses_42"
        assert json.loads(result.stdout)["customerQuote"] == QUOTE

    def test_a_blank_quote_never_reaches_the_server(self, tmp_path) -> None:
        with _server(200, {}) as requests:
            result = _invoke(
                ["allow-setup-commit", "story-1", "--customer-quote", "  "], _settings(tmp_path)
            )

        assert result.exit_code == 1
        assert requests == []

    def test_an_unknown_story_exits_not_found(self, tmp_path) -> None:
        with _server(404, {"detail": "User story not found."}):
            result = _invoke(
                ["allow-setup-commit", "story-1", "--customer-quote", QUOTE], _settings(tmp_path)
            )

        assert result.exit_code == 4


class TestRevokeSetupCommit:
    def test_deletes_the_permission(self, tmp_path) -> None:
        with _server(204) as requests:
            result = _invoke(
                ["revoke-setup-commit", "story-1"], _settings(tmp_path), json_mode=True
            )

        assert result.exit_code == 0, result.output
        [request] = requests
        assert (request.method, request.url.path) == ("DELETE", PATH)
        assert json.loads(result.stdout) == {"revoked": True, "id": "story-1"}
