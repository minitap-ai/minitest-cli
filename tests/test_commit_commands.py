"""Contract tests for `minitest build from-commit` and `minitest run from-commit`."""

import json
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from typer.testing import CliRunner

from minitest_cli.commands.build import app as build_app
from minitest_cli.commands.run import app as run_app
from tests._commit_transport import apps_list_response, cli_context, make_settings, routed

runner = CliRunner()
SHA = "2c589b1b370be5397f6d8774940c989e9110a625"

TRIGGER_BODY = {
    "builds": [
        {
            "id": "c067f6d0-6e36-4c02-af52-475e4db52092",
            "platform": "web",
            "status": "pending",
            "commitSha": SHA,
            "commitTitle": "Ship every challenge",
            "branch": "main",
            "previewUrl": "https://preview.example",
        }
    ],
    "deduplicated": ["web"],
}


def _batch_body(status: str, story_runs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "id": "2e20026b-04c4-4a5f-b6f0-aa4b5207e3e3",
        "appId": "a0d9820f-5136-4f70-b46b-e5966f56bfb5",
        "tenantId": "92a7a284-7c32-41f4-bb79-2e1a95c69c5a",
        "source": "cli",
        "status": status,
        "commitSha": SHA,
        "createdAt": "2026-08-31T10:00:00Z",
        "targets": [
            {
                "id": "t1",
                "platform": "web",
                "buildId": "01171854-02d8-4f63-ae04-c8c7400fdd64",
                "label": "web",
                "counters": {"status": status, "passed": 0, "criticals": 0, "warnings": 0},
            }
        ],
        "storyRuns": story_runs or [],
    }


class TestBuildFromCommit:
    def _run(
        self, args: list[str], tmp_path: Any, trigger: httpx.Response
    ) -> tuple[Any, list[Any]]:
        settings = make_settings(tmp_path)
        seen: list[Any] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/v1/apps":
                return apps_list_response(settings)
            seen.append(json.loads(request.content))
            return trigger

        with cli_context(settings), routed(handler):
            return runner.invoke(build_app, args), seen

    def test_explicit_sha_and_platform_reach_apps_manager(self, tmp_path: Any) -> None:
        result, seen = self._run(
            ["from-commit", SHA, "--platform", "web"],
            tmp_path,
            httpx.Response(201, json=TRIGGER_BODY),
        )

        assert result.exit_code == 0, result.output
        assert seen == [{"forceFullBuild": False, "commitSha": SHA, "platforms": ["web"]}]
        assert json.loads(result.stdout)["builds"][0] == {
            "buildId": "c067f6d0-6e36-4c02-af52-475e4db52092",
            "platform": "web",
            "status": "pending",
            "commitSha": SHA,
            "commitTitle": "Ship every challenge",
            "branch": "main",
            "previewUrl": "https://preview.example",
        }

    def test_omitted_sha_sends_no_commit_so_the_server_uses_default_branch_head(
        self, tmp_path: Any
    ) -> None:
        result, seen = self._run(
            ["from-commit", "--platform", "web", "--force-full"],
            tmp_path,
            httpx.Response(201, json=TRIGGER_BODY),
        )

        assert result.exit_code == 0, result.output
        assert seen == [{"forceFullBuild": True, "platforms": ["web"]}]

    def test_disconnected_repository_is_reported_with_a_fix(self, tmp_path: Any) -> None:
        result, seen = self._run(
            ["from-commit", SHA, "--platform", "web"],
            tmp_path,
            httpx.Response(400, json={"message": "App has no source repository configured"}),
        )

        assert result.exit_code == 1
        assert seen  # the request was attempted
        assert "No GitHub repository is connected" in result.output
        assert "Connect a GitHub repository" in result.output

    @pytest.mark.parametrize(
        ("args", "expected"),
        [
            (["from-commit", "deadbeef", "--platform", "web"], "Invalid commit SHA"),
            (["from-commit", SHA.upper(), "--platform", "web"], "Invalid commit SHA"),
            (["from-commit", SHA, "--platform", "windows"], "Unknown platform"),
        ],
    )
    def test_malformed_input_never_reaches_the_network(
        self, tmp_path: Any, args: list[str], expected: str
    ) -> None:
        result, seen = self._run(args, tmp_path, httpx.Response(500))

        assert result.exit_code == 1
        assert seen == []
        assert expected in result.output


class TestRunFromCommit:
    def test_batch_body_carries_the_commit_and_never_a_target(self, tmp_path: Any) -> None:
        settings = make_settings(tmp_path)
        seen: list[Any] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(json.loads(request.content))
            return httpx.Response(201, json=_batch_body("awaiting_build"))

        with cli_context(settings), routed(handler):
            result = runner.invoke(run_app, ["from-commit", SHA, "--platform", "web", "--no-watch"])

        assert result.exit_code == 0, result.output
        assert seen == [{"commitSha": SHA, "platforms": ["web"]}]
        assert json.loads(result.stdout) == {
            "batchId": "2e20026b-04c4-4a5f-b6f0-aa4b5207e3e3",
            "status": "awaiting_build",
            "commitSha": SHA,
            "targets": [
                {
                    "platform": "web",
                    "buildId": "01171854-02d8-4f63-ae04-c8c7400fdd64",
                    "status": "awaiting_build",
                    "passed": 0,
                    "criticals": 0,
                    "warnings": 0,
                }
            ],
            "storyRuns": [],
        }

    def test_watch_polls_until_the_story_runs_appear(self, tmp_path: Any) -> None:
        settings = make_settings(tmp_path)
        states = iter(
            [
                _batch_body("awaiting_build"),
                _batch_body("running"),
                _batch_body(
                    "completed",
                    [
                        {
                            "id": "run-1",
                            "userStoryId": "efe960e1",
                            "userStoryName": "Notification Center",
                            "status": "completed",
                            "createdAt": "2026-08-31T10:05:00Z",
                        }
                    ],
                ),
            ]
        )
        polls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal polls
            if request.method == "POST":
                return httpx.Response(201, json=_batch_body("awaiting_build"))
            polls += 1
            return httpx.Response(200, json=next(states))

        with (
            cli_context(settings),
            routed(handler),
            patch("minitest_cli.commands.run_commit_helpers.POLL_INTERVAL_SECONDS", 0),
        ):
            result = runner.invoke(run_app, ["from-commit", SHA, "--platform", "web"])

        assert result.exit_code == 0, result.output
        assert polls == 3
        payload = json.loads(result.stdout)
        assert payload["status"] == "completed"
        assert [(r["runId"], r["userStory"]) for r in payload["storyRuns"]] == [
            ("run-1", "Notification Center")
        ]
