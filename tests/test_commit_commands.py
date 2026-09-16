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
OTHER_SHA = "9f3c1d2e4b5a6978c0d1e2f3a4b5c6d7e8f90123"
APP_ID = "a0d9820f-5136-4f70-b46b-e5966f56bfb5"

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

# The ids below are the ones observed on DEV while diagnosing the two-id-space
# trap: apps-manager answers `from-commit` with one id, testing-service stores
# the same physical build under another.
APPS_MANAGER_IOS = "7fab7a81-ae3e-4825-a099-b8bced754088"
APPS_MANAGER_ANDROID = "bdf53595-b1df-4e4c-a80d-ef7f040d67dd"
TESTING_IOS = "94bf119b-f397-4643-8762-fbbd45d66c51"
TESTING_ANDROID = "9266e26c-72ef-4341-9ac6-90bc76c3b09a"

NATIVE_TRIGGER_BODY = {
    "builds": [
        {
            "id": APPS_MANAGER_IOS,
            "platform": "ios",
            "status": "pending",
            "commitSha": SHA,
            "commitTitle": "Ship every challenge",
            "branch": "main",
        },
        {
            "id": APPS_MANAGER_ANDROID,
            "platform": "android",
            "status": "pending",
            "commitSha": SHA,
            "commitTitle": "Ship every challenge",
            "branch": "main",
        },
    ],
    "deduplicated": [],
}


def build_row(
    build_id: str,
    *,
    platform: str,
    commit_sha: str = SHA,
    created_at: str = "2026-08-31T10:00:00Z",
) -> dict[str, Any]:
    """One testing-service build list row."""
    return {
        "id": build_id,
        "appId": APP_ID,
        "platform": platform,
        "status": "pending",
        "commitSha": commit_sha,
        "createdAt": created_at,
    }


def builds_list_response(rows: list[dict[str, Any]]) -> httpx.Response:
    return httpx.Response(200, json={"items": rows, "total": len(rows), "page": 1, "pageSize": 100})


DEFAULT_BUILDS = builds_list_response(
    [build_row("f1d4c1a0-0f2e-4a44-9b2a-0d3f2c1b7a55", platform="web")]
)


def unwrapped(text: str) -> str:
    """Collapse rich's console wrapping so phrases can be matched as written."""
    return " ".join(text.split())


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


def invoke_from_commit(
    args: list[str],
    tmp_path: Any,
    trigger: httpx.Response,
    *,
    builds: httpx.Response | None = None,
    builds_error: Exception | None = None,
    json_mode: bool = True,
) -> tuple[Any, list[Any], list[httpx.URL]]:
    """Drive `build from-commit` over a mock transport.

    Returns the CLI result, the trigger request bodies, and the URLs of the
    testing-service build-list lookups the command performed.
    """
    settings = make_settings(tmp_path)
    seen: list[Any] = []
    lookups: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/apps":
            return apps_list_response(settings)
        if request.method == "GET" and request.url.path.endswith("/builds"):
            lookups.append(request.url)
            if builds_error is not None:
                raise builds_error
            return builds if builds is not None else DEFAULT_BUILDS
        seen.append(json.loads(request.content))
        return trigger

    with cli_context(settings, json_mode=json_mode), routed(handler):
        return runner.invoke(build_app, args), seen, lookups


class TestBuildFromCommit:
    def _run(
        self, args: list[str], tmp_path: Any, trigger: httpx.Response
    ) -> tuple[Any, list[Any]]:
        result, seen, _ = invoke_from_commit(args, tmp_path, trigger)
        return result, seen

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
            "appsManagerBuildId": "c067f6d0-6e36-4c02-af52-475e4db52092",
            "testingServiceBuildId": "f1d4c1a0-0f2e-4a44-9b2a-0d3f2c1b7a55",
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


class TestBuildFromCommitIdResolution:
    """`from-commit` returns apps-manager ids; `run start` only takes
    testing-service ids. The command must bridge the two id spaces itself.
    """

    def _native(
        self,
        tmp_path: Any,
        *,
        builds: httpx.Response | None = None,
        builds_error: Exception | None = None,
        json_mode: bool = True,
    ) -> tuple[Any, list[httpx.URL]]:
        result, _, lookups = invoke_from_commit(
            ["from-commit", SHA],
            tmp_path,
            httpx.Response(201, json=NATIVE_TRIGGER_BODY),
            builds=builds,
            builds_error=builds_error,
            json_mode=json_mode,
        )
        return result, lookups

    def _ids(self, result: Any) -> dict[str, dict[str, str | None]]:
        return {
            b["platform"]: {
                "buildId": b["buildId"],
                "appsManagerBuildId": b["appsManagerBuildId"],
                "testingServiceBuildId": b["testingServiceBuildId"],
            }
            for b in json.loads(result.stdout)["builds"]
        }

    def test_resolution_picks_the_row_matching_both_commit_and_platform(
        self, tmp_path: Any
    ) -> None:
        rows = [
            build_row("11111111-1111-4111-8111-111111111111", platform="ios", commit_sha=OTHER_SHA),
            build_row(TESTING_ANDROID, platform="android"),
            build_row(
                "22222222-2222-4222-8222-222222222222",
                platform="android",
                commit_sha=OTHER_SHA,
            ),
            build_row(TESTING_IOS, platform="ios"),
        ]
        result, _ = self._native(tmp_path, builds=builds_list_response(rows))

        assert result.exit_code == 0, result.output
        assert self._ids(result) == {
            "ios": {
                "buildId": APPS_MANAGER_IOS,
                "appsManagerBuildId": APPS_MANAGER_IOS,
                "testingServiceBuildId": TESTING_IOS,
            },
            "android": {
                "buildId": APPS_MANAGER_ANDROID,
                "appsManagerBuildId": APPS_MANAGER_ANDROID,
                "testingServiceBuildId": TESTING_ANDROID,
            },
        }

    def test_resolution_prefers_the_newest_row_when_a_commit_was_built_twice(
        self, tmp_path: Any
    ) -> None:
        # The stale row is listed first, so "newest" has to come from createdAt
        # rather than from the order the server happened to return.
        rows = [
            build_row(
                "33333333-3333-4333-8333-333333333333",
                platform="ios",
                created_at="2026-08-31T09:00:00Z",
            ),
            build_row(TESTING_IOS, platform="ios", created_at="2026-08-31T12:30:00Z"),
            build_row(TESTING_ANDROID, platform="android"),
        ]
        result, _ = self._native(tmp_path, builds=builds_list_response(rows))

        assert result.exit_code == 0, result.output
        assert self._ids(result)["ios"]["testingServiceBuildId"] == TESTING_IOS

    def test_resolution_asks_for_pending_builds_which_the_list_hides_by_default(
        self, tmp_path: Any
    ) -> None:
        # A build is `pending` the instant it is triggered, and `build list`
        # answers with completed builds only unless statuses are requested.
        _, lookups = self._native(tmp_path)

        assert len(lookups) == 1
        statuses = lookups[0].params.get_list("status")
        assert "pending" in statuses
        assert {"completed", "failed", "cancelled"} <= set(statuses)

    def test_unmatched_commit_reports_a_null_id_without_failing_the_trigger(
        self, tmp_path: Any
    ) -> None:
        rows = [build_row(TESTING_IOS, platform="ios", commit_sha=OTHER_SHA)]
        result, _ = self._native(tmp_path, builds=builds_list_response(rows))

        assert result.exit_code == 0, result.output
        ids = self._ids(result)
        assert ids["ios"]["testingServiceBuildId"] is None
        assert ids["ios"]["buildId"] == APPS_MANAGER_IOS

    @pytest.mark.parametrize(
        ("builds", "builds_error"),
        [
            (httpx.Response(500, json={"message": "boom"}), None),
            (httpx.Response(200, json={"unexpected": "shape"}), None),
            (None, httpx.ConnectTimeout("lookup timed out")),
        ],
    )
    def test_failed_lookup_reports_a_null_id_without_failing_the_trigger(
        self, tmp_path: Any, builds: httpx.Response | None, builds_error: Exception | None
    ) -> None:
        result, _ = self._native(tmp_path, builds=builds, builds_error=builds_error)

        assert result.exit_code == 0, result.output
        ids = self._ids(result)
        assert [ids[p]["testingServiceBuildId"] for p in ("ios", "android")] == [None, None]
        assert ids["android"]["buildId"] == APPS_MANAGER_ANDROID

    def test_human_output_names_the_run_start_flag_for_the_resolved_id(self, tmp_path: Any) -> None:
        rows = [
            build_row(TESTING_IOS, platform="ios"),
            build_row(TESTING_ANDROID, platform="android"),
        ]
        result, _ = self._native(tmp_path, builds=builds_list_response(rows), json_mode=False)
        text = unwrapped(result.output)

        assert result.exit_code == 0, result.output
        assert f"apps-manager build id: {APPS_MANAGER_IOS}" in text
        assert f"testing-service build id: {TESTING_IOS}" in text
        assert f"testing-service build id: {TESTING_ANDROID}" in text
        assert "pass this to `minitest run start --ios-build`" in text
        assert "pass this to `minitest run start --android-build`" in text

    def test_human_output_warns_when_the_testing_service_id_cannot_be_resolved(
        self, tmp_path: Any
    ) -> None:
        result, _ = self._native(
            tmp_path, builds=httpx.Response(503, json={"message": "down"}), json_mode=False
        )
        text = unwrapped(result.output)

        assert result.exit_code == 0, result.output
        assert "testing-service build id: unresolved" in text
        assert "Could not resolve the testing-service build id for ios" in text
        assert "`minitest run start --ios-build` rejects the apps-manager id above" in text
        assert "Run `minitest build list --platform android`" in text


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
