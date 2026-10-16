"""`minitest draft message|messages|stop|update` and the lifecycle commands."""

import json

import httpx

from tests.draft_backend import DRAFT_ID, Backend, draft, invoke

ONE = f"/api/v1/drafts/{DRAFT_ID}"


def _posted(request: httpx.Request) -> httpx.Response:
    sent = json.loads(request.content)
    return httpx.Response(
        202,
        json={
            "messageId": "m1",
            "clientMessageId": sent["clientMessageId"],
            "created": True,
            "draft": draft(),
        },
    )


class TestMessage:
    def test_message_posts_with_a_generated_client_message_id(self):
        backend = Backend().on("POST", f"{ONE}/messages", _posted)

        result = invoke(backend, ["--json", "draft", "message", DRAFT_ID, "--message", "Also iOS"])

        assert result.exit_code == 0, result.output
        [body] = backend.sent("POST", f"{ONE}/messages")
        assert body is not None
        assert body["message"] == "Also iOS"
        assert body["clientMessageId"].startswith("cli-")
        assert json.loads(result.stdout)["created"] is True

    def test_message_keeps_the_given_id_across_a_retry(self):
        backend = Backend().on("POST", f"{ONE}/messages", httpx.Response(503), _posted)

        result = invoke(
            backend,
            ["draft", "message", DRAFT_ID, "--message", "x", "--client-message-id", "turn-2"],
        )

        assert result.exit_code == 0, result.output
        ids = [b["clientMessageId"] for b in backend.sent("POST", f"{ONE}/messages") if b]
        assert ids == ["turn-2", "turn-2"]

    def test_messages_lists_the_last_n(self):
        messages = [{"id": str(i), "role": "user", "content": f"m{i}"} for i in range(3)]
        backend = Backend().on(
            "GET", f"{ONE}/messages", httpx.Response(200, json={"messages": messages})
        )

        result = invoke(backend, ["--json", "draft", "messages", DRAFT_ID, "--last", "2"])

        assert [m["content"] for m in json.loads(result.stdout)] == ["m1", "m2"]

    def test_message_on_a_closed_draft_exits_6(self):
        backend = Backend().on(
            "POST", f"{ONE}/messages", httpx.Response(409, json={"detail": "closed"})
        )

        result = invoke(backend, ["draft", "message", DRAFT_ID, "--message", "x"])

        assert result.exit_code == 6
        assert len(backend.sent("POST", f"{ONE}/messages")) == 1

    def test_stop_reports_whether_mini_was_interrupted(self):
        backend = Backend().on("POST", f"{ONE}/stop", httpx.Response(200, json={"stopped": True}))

        result = invoke(backend, ["--json", "draft", "stop", DRAFT_ID])

        assert json.loads(result.stdout) == {"stopped": True}


class TestUpdateAndLifecycle:
    def test_update_sends_only_the_flags_given(self):
        backend = Backend().on("PATCH", ONE, httpx.Response(200, json=draft(autoMerge=True)))

        result = invoke(backend, ["draft", "update", DRAFT_ID, "--auto-merge", "--no-auto-check"])

        assert result.exit_code == 0, result.output
        assert backend.sent("PATCH", ONE) == [{"autoMerge": True, "autoCheck": False}]

    def test_update_without_flags_is_refused(self):
        result = invoke(Backend(), ["draft", "update", DRAFT_ID])

        assert result.exit_code == 1

    def test_check_sends_story_ids(self):
        story = "cccccccc-0000-0000-0000-000000000001"
        backend = Backend().on("POST", f"{ONE}/check", httpx.Response(200, json=draft()))

        result = invoke(backend, ["draft", "check", DRAFT_ID, "--story", story])

        assert result.exit_code == 0, result.output
        assert backend.sent("POST", f"{ONE}/check") == [
            {"includeWaiting": False, "storyIds": [story]}
        ]

    def test_merge_of_a_draft_not_ready_exits_6_without_retrying(self):
        backend = Backend().on(
            "POST", f"{ONE}/merge", httpx.Response(409, json={"detail": "not ready"})
        )

        result = invoke(backend, ["draft", "merge", DRAFT_ID])

        assert result.exit_code == 6
        assert "not ready" in result.output
        assert len(backend.sent("POST", f"{ONE}/merge")) == 1

    def test_build_and_not_a_bug_post_their_bodies(self):
        story = "cccccccc-0000-0000-0000-000000000001"
        backend = (
            Backend()
            .on("POST", f"{ONE}/build", httpx.Response(202, json=draft()))
            .on("POST", f"{ONE}/stories/{story}/not-a-bug", httpx.Response(200, json=draft()))
        )

        assert invoke(backend, ["draft", "build", DRAFT_ID, "--ref", "main"]).exit_code == 0
        result = invoke(backend, ["draft", "not-a-bug", DRAFT_ID, story, "--reason", "flaky"])

        assert result.exit_code == 0, result.output
        assert backend.sent("POST", f"{ONE}/build") == [{"ref": "main"}]
        assert backend.sent("POST", f"{ONE}/stories/{story}/not-a-bug") == [{"reason": "flaky"}]

    def test_rejected_key_exits_1_and_unknown_draft_exits_4(self):
        backend = Backend().on("POST", f"{ONE}/discard", httpx.Response(403, json={"detail": "no"}))
        assert invoke(backend, ["draft", "discard", DRAFT_ID]).exit_code == 1

        assert invoke(Backend(), ["draft", "revert", DRAFT_ID]).exit_code == 4
