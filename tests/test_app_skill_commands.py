"""`app-skill` and `scenario-binding set-app-skills` against a recorded testing-service contract."""

import json

import httpx
import pytest
from typer.testing import CliRunner

from minitest_cli.commands.app_skill import app as skill_app
from minitest_cli.commands.user_story_bindings import app as binding_app
from tests._commit_transport import cli_context, make_settings, routed

runner = CliRunner()
_APP = "a0d9820f-5136-4f70-b46b-e5966f56bfb5"
_SKILLS = f"/api/v1/apps/{_APP}/skills"


def _skill(**overrides):
    skill = {
        "id": "5b8f3f43-0000-4000-8000-000000000001",
        "name": "clutch-test-backend",
        "description": "Use to arrange markets, balances and bets.",
        "platforms": [],
        "instructions": 'curl -H "Authorization: Bearer $CLUTCH_TEST_API_KEY" ...',
        "version": 1,
        "secretNames": [],
        "undefinedSecrets": ["CLUTCH_TEST_API_KEY"],
        "openProposal": None,
        "createdAt": "2026-10-01T10:00:00Z",
        "updatedAt": "2026-10-01T10:00:00Z",
    }
    return {**skill, **overrides}


class Recorder:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.response

    @property
    def body(self) -> dict:
        return json.loads(self.requests[-1].content)


def _invoke(app, args, recorder, tmp_path, *, json_mode=False, stdin=None):
    with routed(recorder), cli_context(make_settings(tmp_path), json_mode=json_mode):
        return runner.invoke(app, args, input=stdin)


def test_create_sends_instructions_file_and_warns_about_undefined_secret(tmp_path):
    procedure = tmp_path / "skill.md"
    procedure.write_text('curl -H "Authorization: Bearer $CLUTCH_TEST_API_KEY" ...')
    recorder = Recorder(httpx.Response(201, json=_skill()))

    result = _invoke(
        skill_app,
        [
            "create",
            "clutch-test-backend",
            "--description",
            "Use to arrange markets.",
            "--platform",
            "ios",
            "--instructions-file",
            str(procedure),
        ],
        recorder,
        tmp_path,
    )

    assert result.exit_code == 0, result.output
    assert recorder.requests[0].method == "POST"
    assert recorder.requests[0].url.path == _SKILLS
    assert recorder.body == {
        "name": "clutch-test-backend",
        "description": "Use to arrange markets.",
        "platforms": ["ios"],
        "instructions": procedure.read_text(),
    }
    assert "$CLUTCH_TEST_API_KEY" in result.output
    assert "secret set clutch-test-backend" in result.output


def test_update_all_platforms_clears_the_platform_filter(tmp_path):
    recorder = Recorder(httpx.Response(200, json=_skill(version=2)))

    result = _invoke(
        skill_app, ["update", "clutch-test-backend", "--all-platforms"], recorder, tmp_path
    )

    assert result.exit_code == 0, result.output
    assert recorder.requests[0].method == "PATCH"
    assert recorder.body == {"platforms": []}


def test_delete_linked_skill_lists_scenarios_and_keeps_the_skill(tmp_path):
    recorder = Recorder(
        httpx.Response(
            409,
            json={
                "error": "skill_linked",
                "message": "This skill is linked to scenarios. Unlink them to delete it.",
                "linkedScenarios": [{"id": "s1", "name": "Voided market refunds the stake"}],
            },
        )
    )

    result = _invoke(skill_app, ["delete", "clutch-test-backend"], recorder, tmp_path)

    assert result.exit_code == 6
    assert "Voided market refunds the stake" in result.output
    assert "--unlink-scenarios --yes" in result.output
    assert "unlinkScenarios" not in str(recorder.requests[0].url)


def test_delete_with_unlink_requires_yes_before_calling_the_api(tmp_path):
    recorder = Recorder(httpx.Response(204))

    refused = _invoke(
        skill_app, ["delete", "clutch-test-backend", "--unlink-scenarios"], recorder, tmp_path
    )
    confirmed = _invoke(
        skill_app,
        ["delete", "clutch-test-backend", "--unlink-scenarios", "--yes"],
        recorder,
        tmp_path,
    )

    assert refused.exit_code == 1
    assert confirmed.exit_code == 0, confirmed.output
    assert len(recorder.requests) == 1
    assert recorder.requests[0].url.params["unlinkScenarios"] == "true"


def test_secret_set_reads_stdin_and_never_echoes_the_value(tmp_path):
    recorder = Recorder(
        httpx.Response(200, json={"name": "CLUTCH_TEST_API_KEY", "version": 1, "updatedAt": "now"})
    )

    result = _invoke(
        skill_app,
        ["secret", "set", "clutch-test-backend", "CLUTCH_TEST_API_KEY"],
        recorder,
        tmp_path,
        stdin="s3cr3t-value\n",
    )

    assert result.exit_code == 0, result.output
    assert recorder.body == {"name": "CLUTCH_TEST_API_KEY", "value": "s3cr3t-value"}
    assert "s3cr3t-value" not in result.output


def test_propose_sends_the_reason_with_the_change(tmp_path):
    recorder = Recorder(httpx.Response(200, json={"id": "p1", "status": "open"}))

    result = _invoke(
        skill_app,
        [
            "propose",
            "clutch-test-backend",
            "--reason",
            "Run #482: 422 category required",
            "--instructions",
            "POST /markets with category",
        ],
        recorder,
        tmp_path,
    )

    assert result.exit_code == 0, result.output
    assert recorder.requests[0].url.path == f"{_SKILLS}/clutch-test-backend/proposals"
    assert recorder.body == {
        "instructions": "POST /markets with category",
        "reason": "Run #482: 422 category required",
    }


@pytest.mark.parametrize(
    ("status", "body", "exit_code", "message"),
    [
        (404, {"message": "Skills are not enabled for this workspace."}, 4, "not enabled"),
        (401, {"message": "Invalid API key"}, 1, "Authentication failed (401)"),
        (
            422,
            {
                "error": "validation_error",
                "message": "Request validation failed",
                "details": {
                    "errors": [{"field": "body.name", "message": "String should match pattern"}]
                },
            },
            1,
            "name: String should match pattern",
        ),
    ],
)
def test_backend_refusals_map_to_documented_exit_codes(tmp_path, status, body, exit_code, message):
    recorder = Recorder(httpx.Response(status, json=body))

    result = _invoke(skill_app, ["list"], recorder, tmp_path)

    assert result.exit_code == exit_code
    assert message in result.output


def test_set_skills_replaces_the_scenario_links(tmp_path):
    recorder = Recorder(httpx.Response(200, json={"skills": []}))

    result = _invoke(binding_app, ["set-app-skills", "story-1", "--clear"], recorder, tmp_path)
    linked = _invoke(
        binding_app,
        ["set-app-skills", "story-1", "--skill", "clutch-test-backend"],
        recorder,
        tmp_path,
    )

    assert result.exit_code == 0, result.output
    assert linked.exit_code == 0, linked.output
    assert recorder.requests[0].url.path == f"/api/v1/apps/{_APP}/user-stories/story-1/skills"
    assert json.loads(recorder.requests[0].content) == {"skillNames": []}
    assert json.loads(recorder.requests[1].content) == {"skillNames": ["clutch-test-backend"]}
