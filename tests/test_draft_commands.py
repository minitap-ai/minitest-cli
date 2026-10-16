"""`minitest draft`: open a draft for Mini, talk to it, watch it, act on the result."""

import json
from unittest.mock import AsyncMock, patch

import httpx

from tests.draft_backend import DRAFT_ID, Backend, draft, invoke

DRAFTS = "/api/v1/drafts"
ONE = f"{DRAFTS}/{DRAFT_ID}"


def _created(request: httpx.Request) -> httpx.Response:
    return httpx.Response(201, json=draft(title=json.loads(request.content).get("title")))


class TestCreate:
    def test_create_inline_message_opens_one_draft_with_a_key(self):
        backend = Backend().on("POST", DRAFTS, _created)

        result = invoke(backend, ["--json", "draft", "create", "--message", "Add a refund test"])

        assert result.exit_code == 0, result.output
        [body] = backend.sent("POST", DRAFTS)
        assert body is not None
        assert body["message"] == "Add a refund test"
        assert body["idempotencyKey"].startswith("cli-")
        assert (body["autoCheck"], body["autoMerge"]) == (False, False)
        assert json.loads(result.stdout)["id"] == DRAFT_ID

    def test_create_message_file_from_stdin_with_flags(self):
        backend = Backend().on("POST", DRAFTS, _created)

        result = invoke(
            backend,
            [
                "draft",
                "create",
                "--message-file",
                "-",
                "--auto-check",
                "--auto-merge",
                "--title",
                "Refunds",
                "--idempotency-key",
                "k-1",
            ],
            stdin="Cover refunds\n",
        )

        assert result.exit_code == 0, result.output
        [body] = backend.sent("POST", DRAFTS)
        assert body is not None
        assert body == body | {
            "message": "Cover refunds\n",
            "autoCheck": True,
            "autoMerge": True,
            "title": "Refunds",
            "idempotencyKey": "k-1",
        }

    def test_create_retries_a_server_error_with_the_same_key(self):
        backend = Backend().on("POST", DRAFTS, httpx.Response(502), _created)

        result = invoke(backend, ["--json", "draft", "create", "--message", "hi"])

        assert result.exit_code == 0, result.output
        first, second = backend.sent("POST", DRAFTS)
        assert first is not None and second is not None
        assert first["idempotencyKey"] == second["idempotencyKey"]

    def test_create_both_message_sources_is_refused_before_any_call(self, tmp_path):
        backend = Backend()
        message_file = tmp_path / "m.txt"
        message_file.write_text("x")

        result = invoke(
            backend, ["draft", "create", "--message", "a", "--message-file", str(message_file)]
        )

        assert result.exit_code == 1
        assert backend.requests == []

    def test_create_without_message_is_refused(self):
        result = invoke(Backend(), ["draft", "create", "--title", "x"])

        assert result.exit_code == 1


class TestGetWatch:
    def test_watch_returns_once_mini_is_idle(self):
        backend = Backend().on(
            "GET",
            ONE,
            httpx.Response(200, json=draft(miniWriting=True, stateReasonCode="authoring")),
            httpx.Response(200, json=draft(stateReasonCode="not_checked", state="drafting")),
        )

        with patch("minitest_cli.commands.draft_watch.asyncio.sleep", AsyncMock()):
            result = invoke(backend, ["--json", "draft", "get", DRAFT_ID, "--watch"])

        assert result.exit_code == 0, result.output
        assert len(backend.sent("GET", ONE)) == 2
        assert json.loads(result.stdout)["stateReasonCode"] == "not_checked"

    def test_watch_settled_also_waits_for_the_check(self):
        idle_validating = draft(state="validating", stateReasonCode=None)
        backend = Backend().on(
            "GET",
            ONE,
            httpx.Response(200, json=idle_validating),
            httpx.Response(200, json=draft(state="ready", stateReasonCode=None)),
        )

        with patch("minitest_cli.commands.draft_watch.asyncio.sleep", AsyncMock()):
            result = invoke(
                backend, ["--json", "draft", "get", DRAFT_ID, "--watch", "--until", "settled"]
            )

        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["state"] == "ready"

    def test_watch_settled_waits_for_a_check_the_state_does_not_show_yet(self):
        started = draft(stateReasonCode="not_checked", counts={"validating": 1})
        backend = Backend().on(
            "GET",
            ONE,
            httpx.Response(200, json=started),
            httpx.Response(200, json=draft(state="ready", stateReasonCode=None)),
        )

        with patch("minitest_cli.commands.draft_watch.asyncio.sleep", AsyncMock()):
            result = invoke(
                backend, ["--json", "draft", "get", DRAFT_ID, "--watch", "--until", "settled"]
            )

        assert result.exit_code == 0, result.output
        assert len(backend.sent("GET", ONE)) == 2

    def test_watch_stops_on_a_question_for_the_user(self):
        backend = Backend().on("GET", ONE, httpx.Response(200, json=draft(needsUser=True)))

        result = invoke(backend, ["--json", "draft", "get", DRAFT_ID, "--watch"])

        assert result.exit_code == 0
        assert len(backend.sent("GET", ONE)) == 1

    def test_watch_timeout_prints_the_last_snapshot_and_exits_1(self):
        backend = Backend().on("GET", ONE, httpx.Response(200, json=draft(miniWriting=True)))
        clock = iter([0.0, 0.0, 5.0, 5.0, 5.0])

        with (
            patch("minitest_cli.commands.draft_watch.asyncio.sleep", AsyncMock()),
            patch("minitest_cli.commands.draft_watch._now", lambda: next(clock)),
        ):
            result = invoke(
                backend, ["--json", "draft", "get", DRAFT_ID, "--watch", "--timeout", "2"]
            )

        assert result.exit_code == 1
        assert json.loads(result.stdout)["miniWriting"] is True

    def test_get_rejects_a_non_uuid_id(self):
        result = invoke(Backend(), ["draft", "get", "nope"])

        assert result.exit_code == 1
