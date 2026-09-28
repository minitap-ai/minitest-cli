"""Tests for suite-change provenance contract (section 3).

Uses real httpx request cycles via MockTransport so headers are proven at
the HTTP wire level rather than by inspecting mock call args.
"""

import json

import httpx
from typer.testing import CliRunner

from minitest_cli.commands.draft_feature import app as df_app
from tests._commit_transport import cli_context, make_settings, routed

runner = CliRunner()

_APP_ID = "a0d9820f-5136-4f70-b46b-e5966f56bfb5"
_FEATURE_PAYLOAD = {
    "id": "b1",
    "tenantId": "t1",
    "appId": _APP_ID,
    "title": "Checkout",
    "description": "test branch",
    "status": "open",
    "rebaseState": "in_sync",
    "rebasedToMainRev": 1,
    "sourceRefs": [],
    "createdAt": "2026-01-01T00:00:00Z",
    "updatedAt": "2026-01-01T00:00:00Z",
    "mergedAt": None,
}


class TestProvenanceHeaders:
    """X-Minitest-Conversation-Id and X-Minitest-Cause are sent on every request."""

    def test_headers_present_when_env_vars_set(self, tmp_path):
        """Both provenance headers appear when their env vars are set."""
        received: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            received["conversation_id"] = request.headers.get("x-minitest-conversation-id", "")
            received["cause"] = request.headers.get("x-minitest-cause", "")
            return httpx.Response(201, json=_FEATURE_PAYLOAD)

        settings = make_settings(
            tmp_path,
            conversation_id="conv-abc-123",
            cause="ci/pipeline",
        )
        with routed(handler), cli_context(settings, json_mode=True):
            result = runner.invoke(df_app, ["create", "--title", "Checkout"])

        assert result.exit_code == 0, result.output
        assert received["conversation_id"] == "conv-abc-123"
        assert received["cause"] == "ci/pipeline"

    def test_headers_absent_when_env_vars_not_set(self, tmp_path):
        """Neither header is sent when the env vars are absent."""
        received_keys: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            received_keys.extend(request.headers.keys())
            return httpx.Response(201, json=_FEATURE_PAYLOAD)

        settings = make_settings(tmp_path)
        with routed(handler), cli_context(settings, json_mode=True):
            result = runner.invoke(df_app, ["create", "--title", "Checkout"])

        assert result.exit_code == 0, result.output
        assert "x-minitest-conversation-id" not in received_keys
        assert "x-minitest-cause" not in received_keys


class TestDfCreateSourceRefs:
    """--source-refs flag is passed as sourceRefs in the POST body."""

    def test_source_refs_included_in_post_body(self, tmp_path):
        received_body: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            received_body.update(json.loads(request.content))
            return httpx.Response(201, json=_FEATURE_PAYLOAD)

        source_refs = [{"type": "github_pr", "ref": "https://github.com/org/repo/pull/42"}]
        settings = make_settings(tmp_path)
        with routed(handler), cli_context(settings, json_mode=True):
            result = runner.invoke(
                df_app,
                ["create", "--title", "Checkout", "--source-refs", json.dumps(source_refs)],
            )

        assert result.exit_code == 0, result.output
        assert received_body["sourceRefs"] == source_refs

    def test_source_refs_absent_when_flag_not_given(self, tmp_path):
        received_body: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            received_body.update(json.loads(request.content))
            return httpx.Response(201, json=_FEATURE_PAYLOAD)

        settings = make_settings(tmp_path)
        with routed(handler), cli_context(settings, json_mode=True):
            result = runner.invoke(df_app, ["create", "--title", "Checkout"])

        assert result.exit_code == 0, result.output
        assert "sourceRefs" not in received_body
