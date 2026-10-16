"""`minitest draft ask`: answering Mini, with secrets kept off the command line and output."""

import json

import httpx

from tests.draft_backend import ASK_ID, DRAFT_ID, Backend, draft, invoke

ONE = f"/api/v1/drafts/{DRAFT_ID}"
ANSWER = f"{ONE}/asks/{ASK_ID}/answer"
SECRET = "hunter2-very-secret"
ASK = {
    "id": ASK_ID,
    "question": "Which test account should Mini use?",
    "state": "open",
    "askType": "credentials",
    "answerFields": [
        {"key": "email", "label": "Email", "secret": False, "required": True},
        {"key": "password", "label": "Password", "secret": True, "required": True},
    ],
}


def _backend() -> Backend:
    return (
        Backend()
        .on("GET", ONE, httpx.Response(200, json=draft(asks=[ASK], needsUser=True)))
        .on("POST", ANSWER, httpx.Response(200, json=draft()))
    )


class TestAsks:
    def test_list_shows_the_fields_each_answer_takes(self):
        result = invoke(_backend(), ["--json", "draft", "ask", "list", DRAFT_ID])

        assert result.exit_code == 0, result.output
        [ask] = json.loads(result.stdout)
        assert [f["key"] for f in ask["answerFields"]] == ["email", "password"]

    def test_secret_from_stdin_is_sent_and_never_printed(self):
        backend = _backend()

        result = invoke(
            backend,
            [
                "--json",
                "draft",
                "ask",
                "answer",
                DRAFT_ID,
                ASK_ID,
                "--field",
                "email=qa@shop.test",
                "--field-file",
                "password=-",
            ],
            stdin=SECRET + "\n",
        )

        assert result.exit_code == 0, result.output
        assert backend.sent("POST", ANSWER) == [
            {"fields": {"email": "qa@shop.test", "password": SECRET}}
        ]
        assert SECRET not in result.output

    def test_secret_from_a_file(self, tmp_path):
        backend = _backend()
        secret_file = tmp_path / "pw"
        secret_file.write_text(SECRET)

        result = invoke(
            backend,
            ["draft", "ask", "answer", DRAFT_ID, ASK_ID, "--field-file", f"password={secret_file}"],
        )

        assert result.exit_code == 0, result.output
        assert backend.sent("POST", ANSWER) == [{"fields": {"password": SECRET}}]
        assert SECRET not in result.output

    def test_secret_on_the_command_line_is_refused_before_sending(self):
        backend = _backend()

        result = invoke(
            backend, ["draft", "ask", "answer", DRAFT_ID, ASK_ID, "--field", f"password={SECRET}"]
        )

        assert result.exit_code == 1
        assert backend.sent("POST", ANSWER) == []
        assert SECRET not in result.output

    def test_free_text_answer(self):
        backend = _backend()

        result = invoke(backend, ["draft", "ask", "answer", DRAFT_ID, ASK_ID, "--answer", "Use QA"])

        assert result.exit_code == 0, result.output
        assert backend.sent("POST", ANSWER) == [{"answer": "Use QA"}]

    def test_unknown_field_and_unknown_ask_are_refused(self):
        backend = _backend()
        unknown_field = invoke(
            backend, ["draft", "ask", "answer", DRAFT_ID, ASK_ID, "--field", "pin=1"]
        )
        other_ask = "eeeeeeee-0000-0000-0000-000000000009"
        unknown_ask = invoke(
            backend, ["draft", "ask", "answer", DRAFT_ID, other_ask, "--answer", "x"]
        )

        assert unknown_field.exit_code == 1
        assert unknown_ask.exit_code == 4
        assert backend.sent("POST", ANSWER) == []

    def test_decline_with_reason(self):
        decline = f"{ONE}/asks/{ASK_ID}/decline"
        backend = Backend().on("POST", decline, httpx.Response(200, json=draft()))

        result = invoke(backend, ["draft", "ask", "decline", DRAFT_ID, ASK_ID, "--reason", "n/a"])

        assert result.exit_code == 0, result.output
        assert backend.sent("POST", decline) == [{"reason": "n/a"}]
