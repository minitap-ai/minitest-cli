"""`minitest secret lint|extract` against a mocked testing-service."""

import json

import httpx
import pytest

from minitest_cli.commands.secret import app
from minitest_cli.commands.secret_extract import literal_of
from tests._secret_router import FAKE, SECRETS, STORIES, Router, invoke, secret_row, vault

_LINT = f"{SECRETS}/lint"
_STORY_PATH = f"{STORIES}/s1"


def _story(description: str, criteria: list[str]) -> dict:
    return {
        "id": "s1",
        "name": "Login",
        "description": description,
        "acceptanceCriteria": [
            {"criterionId": f"c{i}", "content": c} for i, c in enumerate(criteria, start=1)
        ],
    }


class LintRouter(Router):
    """Answers /lint by finding ``FAKE`` (and its labelled form) in the posted text."""

    def __init__(self, routes, *, extra_leak: str | None = None) -> None:
        super().__init__(routes)
        self.extra_leak = extra_leak

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path != _LINT:
            return super().__call__(request)
        self.requests.append(request)
        text = json.loads(request.content)["text"]
        leaks = []
        for literal in filter(None, [FAKE, self.extra_leak]):
            if literal in text:
                start = text.index(literal)
                leaks.append({"start": start, "end": start + len(literal)})
        refs = [{"name": "ADMIN_PASSWORD", "start": 0, "end": 1}] if "{{secret:" in text else []
        missing = ["GHOST"] if "GHOST" in text else []
        legacy = ["OLD"] if "$OLD" in text else []
        pending = ["SANDBOX_KEY"] if "SANDBOX_KEY" in text else []
        body = {"references": refs, "missing": missing, "leaks": leaks, "legacy": legacy}
        body |= {"pending": pending}
        return httpx.Response(200, json=body)


class TestLint:
    def test_lint_text_clean(self, tmp_path):
        result = invoke(
            app,
            ["lint", "--text", "log in with {{secret:ADMIN_PASSWORD}}"],
            LintRouter({}),
            tmp_path,
        )
        assert result.exit_code == 0, result.output
        assert "reference {{secret:ADMIN_PASSWORD}}" in result.output

    def test_lint_text_leak_exits_1_without_printing_value(self, tmp_path):
        result = invoke(
            app, ["lint", "--text", f"line one\npassword {FAKE}"], LintRouter({}), tmp_path
        )
        assert result.exit_code == 1
        assert "2:10-2:23" in result.output
        assert FAKE not in result.output

    def test_lint_file_missing_and_legacy(self, tmp_path):
        path = tmp_path / "skill.md"
        path.write_text("curl {{secret:GHOST}} $OLD")
        result = invoke(app, ["lint", "--file", str(path)], LintRouter({}), tmp_path)
        assert result.exit_code == 1
        assert "GHOST is referenced but not set" in result.output
        assert "$OLD is legacy syntax" in result.output

    def test_lint_scenario_json(self, tmp_path):
        story = httpx.Response(200, json=_story("Open the app", [f"type {FAKE}"]))
        router = LintRouter({("GET", _STORY_PATH): story})
        result = invoke(app, ["lint", "--scenario", "s1", "--json"], router, tmp_path)
        assert result.exit_code == 1
        payload = json.loads(result.stdout)
        assert payload["ok"] is False
        assert [s["source"] for s in payload["sources"]] == ["description", "criterion 1"]

    def test_lint_pending_warns_without_failing(self, tmp_path):
        text = "use {{secret:SANDBOX_KEY}}"
        result = invoke(app, ["lint", "--text", text], LintRouter({}), tmp_path)
        assert result.exit_code == 0, result.output
        assert "SANDBOX_KEY has no value yet" in result.output

    def test_lint_pending_json(self, tmp_path):
        text = "use {{secret:SANDBOX_KEY}}"
        result = invoke(app, ["lint", "--text", text, "--json"], LintRouter({}), tmp_path)
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["sources"][0]["pending"] == ["SANDBOX_KEY"]

    def test_lint_requires_exactly_one_source(self, tmp_path):
        assert invoke(app, ["lint"], LintRouter({}), tmp_path).exit_code == 1

    def test_lint_flag_off(self, tmp_path):
        router = Router({("POST", _LINT): httpx.Response(404, json={"detail": "Not Found"})})
        result = invoke(app, ["lint", "--text", "x"], router, tmp_path)
        assert result.exit_code == 4
        assert "not enabled" in result.output


class TestExtract:
    def _router(self, story, *, secrets=None, extra_leak=None):
        return LintRouter(
            {
                ("GET", SECRETS): vault(secrets or []),
                ("GET", _STORY_PATH): httpx.Response(200, json=story),
                ("PUT", f"{SECRETS}/ADMIN_PASSWORD"): httpx.Response(201, json=secret_row()),
                ("PATCH", _STORY_PATH): httpx.Response(200, json=story),
            },
            extra_leak=extra_leak,
        )

    _ARGS = ["extract", "s1", "--as", "ADMIN_PASSWORD", "--kind", "password"]

    def test_extract_creates_secret_and_rewrites_scenario(self, tmp_path):
        story = _story(f"Log in with {FAKE}", ["Open", f"type {FAKE} again"])
        router = self._router(story)
        result = invoke(app, self._ARGS, router, tmp_path)
        assert result.exit_code == 0, result.output
        assert router.body("PUT", f"{SECRETS}/ADMIN_PASSWORD") == {
            "kind": "password",
            "value": FAKE,
        }
        patch = router.body("PATCH", _STORY_PATH)
        assert patch["description"] == "Log in with {{secret:ADMIN_PASSWORD}}"
        assert patch["acceptanceCriteria"] == [
            {"id": "c1", "content": "Open"},
            {"id": "c2", "content": "type {{secret:ADMIN_PASSWORD}} again"},
        ]
        assert "2 occurrence(s)" in result.output
        assert FAKE not in result.output

    def test_extract_dry_run_writes_nothing(self, tmp_path):
        router = self._router(_story(f"use {FAKE}", []))
        result = invoke(app, [*self._ARGS, "--dry-run", "--json"], router, tmp_path)
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["replacements"] == 1
        assert not router.called("PUT") and not router.called("PATCH")

    def test_extract_several_literals_needs_leak_choice(self, tmp_path):
        router = self._router(_story(f"{FAKE} and other-secret-9", []), extra_leak="other-secret-9")
        result = invoke(app, self._ARGS, router, tmp_path)
        assert result.exit_code == 1
        assert "choose one with --leak N" in result.output
        assert FAKE not in result.output
        result = invoke(app, [*self._ARGS, "--leak", "2"], router, tmp_path)
        assert result.exit_code == 0, result.output
        assert router.body("PUT", f"{SECRETS}/ADMIN_PASSWORD")["value"] == "other-secret-9"

    def test_extract_refuses_existing_name(self, tmp_path):
        router = self._router(_story(f"use {FAKE}", []), secrets=[secret_row()])
        result = invoke(app, self._ARGS, router, tmp_path)
        assert result.exit_code == 1
        assert "already exists" in result.output
        assert not router.called("PUT")

    def test_extract_no_leak(self, tmp_path):
        result = invoke(app, self._ARGS, self._router(_story("clean", [])), tmp_path)
        assert result.exit_code == 1
        assert "No literal secret" in result.output

    def test_extract_refuses_card_and_agent_context(self, tmp_path):
        router = self._router(_story(f"use {FAKE}", []))
        card = ["extract", "s1", "--as", "CARD", "--kind", "card"]
        assert invoke(app, card, router, tmp_path).exit_code == 1
        result = invoke(app, self._ARGS, router, tmp_path, env={"MINITAP_SECRETS_SOCKET": "/tmp/s"})
        assert result.exit_code == 1
        assert not router.requests


@pytest.mark.parametrize(
    "span, literal",
    [
        ("password: hunter22", "hunter22"),
        ("Pwd is s3cret!", "s3cret!"),
        ("sk_live_ab", "sk_live_ab"),
    ],
)
def test_literal_of_strips_heuristic_label(span, literal):
    assert literal_of(span, {"start": 0, "end": len(span)}) == literal
