"""Tests for minitest_cli.commands.run — start, status, all commands."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import typer
from click.exceptions import Exit
from typer.testing import CliRunner

from minitest_cli.commands.run import app as run_app
from minitest_cli.commands.run_helpers import (
    display_run_result,
    extract_detail,
    format_run_row,
    handle_response_error,
    is_uuid,
)
from minitest_cli.core.config import Settings
from minitest_cli.models.story_run import StoryRunResponse

runner = CliRunner()


# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------


def _make_settings(tmp_path, **overrides):
    defaults = {
        "config_dir": tmp_path,
        "token": "test-token",
        "supabase_url": "https://test.supabase.co",
        "supabase_publishable_key": "test-publishable-key",
        "app_id": "app-123",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _patch_context(settings, json_mode=False, app_flag=None):
    return [
        patch.object(typer.Context, "settings", settings, create=True),
        patch.object(typer.Context, "json_mode", json_mode, create=True),
        patch.object(typer.Context, "app_flag", app_flag, create=True),
    ]


def _run_with_context(args, settings, json_mode=False, app_flag=None):
    patches = _patch_context(settings, json_mode, app_flag)
    for p in patches:
        p.start()
    try:
        return runner.invoke(run_app, args)
    finally:
        for p in patches:
            p.stop()


def _mock_response(status_code: int = 200, json_data: object = None) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = json.dumps(json_data) if json_data else ""
    return resp


def _mock_client() -> AsyncMock:
    """Create a base async mock client with context manager support."""
    client = AsyncMock()
    client.get = AsyncMock()
    client.post = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


# ---------------------------------------------------------------------------
# Fixtures / sample data — matches the real API flat response shape
# ---------------------------------------------------------------------------

_USER_STORY_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
_RUN_UUID = "11111111-2222-3333-4444-555555555555"
_IOS_BUILD_UUID = "b1b1b1b1-b1b1-b1b1-b1b1-b1b1b1b1b1b1"
_ANDROID_BUILD_UUID = "b2b2b2b2-b2b2-b2b2-b2b2-b2b2b2b2b2b2"
_CRITERIA_UUID_1 = "c1c1c1c1-c1c1-c1c1-c1c1-c1c1c1c1c1c1"
_CRITERIA_UUID_2 = "c2c2c2c2-c2c2-c2c2-c2c2-c2c2c2c2c2c2"

_PENDING_RUN = {
    "id": _RUN_UUID,
    "userStoryId": _USER_STORY_UUID,
    "userStoryName": "Login Story",
    "tenantId": "tenant-1",
    "status": "pending",
    "iosBuildId": _IOS_BUILD_UUID,
    "androidBuildId": _ANDROID_BUILD_UUID,
    "iosRecordingPath": None,
    "androidRecordingPath": None,
    "iosRecordingUrl": None,
    "androidRecordingUrl": None,
    "iosErrorMessage": None,
    "androidErrorMessage": None,
    "startedAt": None,
    "finishedAt": None,
    "createdAt": "2025-06-01T10:00:00Z",
    "results": [],
}

_COMPLETED_RUN = {
    "id": _RUN_UUID,
    "userStoryId": _USER_STORY_UUID,
    "userStoryName": "Login Story",
    "tenantId": "tenant-1",
    "status": "completed",
    "iosBuildId": _IOS_BUILD_UUID,
    "androidBuildId": _ANDROID_BUILD_UUID,
    "iosRecordingPath": "recordings/ios.mp4",
    "androidRecordingPath": "recordings/android.mp4",
    "iosRecordingUrl": "https://example.com/ios-rec",
    "androidRecordingUrl": "https://example.com/android-rec",
    "iosErrorMessage": None,
    "androidErrorMessage": None,
    "startedAt": "2025-06-01T10:00:30Z",
    "finishedAt": "2025-06-01T10:05:00Z",
    "createdAt": "2025-06-01T10:00:00Z",
    "results": [
        {
            "id": "r1",
            "storyRunId": _RUN_UUID,
            "criterionVersionId": _CRITERIA_UUID_1,
            "platform": "ios",
            "success": True,
            "failReason": None,
            "createdAt": "2025-06-01T10:05:00Z",
        },
        {
            "id": "r2",
            "storyRunId": _RUN_UUID,
            "criterionVersionId": _CRITERIA_UUID_1,
            "platform": "android",
            "success": False,
            "failReason": "Button not found",
            "createdAt": "2025-06-01T10:05:00Z",
        },
    ],
}

_FAILED_RUN = {
    **_COMPLETED_RUN,
    "status": "failed",
    "iosErrorMessage": "Device crashed",
    "androidErrorMessage": None,
}

_USER_STORY_LIST = {
    "items": [
        {"id": _USER_STORY_UUID, "name": "Login Story", "type": "standard"},
        {
            "id": "ff000000-0000-0000-0000-000000000001",
            "name": "Checkout Story",
            "type": "standard",
        },
    ],
    "total": 2,
    "page": 1,
    "pageSize": 100,
}

_BUILD_FLAGS = ["--ios-build", _IOS_BUILD_UUID, "--android-build", _ANDROID_BUILD_UUID]

_RUN_LIST_RESPONSE = {
    "items": [_COMPLETED_RUN, {**_PENDING_RUN, "id": "22222222-3333-4444-5555-666666666666"}],
    "total": 2,
    "page": 1,
    "pageSize": 20,
}

_BATCH_RESPONSE = {
    "storyRuns": [
        {**_PENDING_RUN, "userStoryName": "Login Story"},
        {
            **_PENDING_RUN,
            "id": "22222222-3333-4444-5555-666666666666",
            "userStoryName": "Checkout Story",
            "userStoryId": "ff000000-0000-0000-0000-000000000001",
        },
    ],
    "message": "Created 2 story runs. 2 queued for execution.",
}


# ---------------------------------------------------------------------------
# Helper unit tests
# ---------------------------------------------------------------------------


class TestIsUuid:
    def test_valid_uuid_returns_true(self) -> None:
        assert is_uuid("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee") is True

    def test_uppercase_uuid_returns_true(self) -> None:
        assert is_uuid("AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE") is True

    def test_name_returns_false(self) -> None:
        assert is_uuid("Login Story") is False

    def test_partial_uuid_returns_false(self) -> None:
        assert is_uuid("aaaaaaaa-bbbb-cccc-dddd") is False

    def test_empty_string_returns_false(self) -> None:
        assert is_uuid("") is False


class TestExtractDetail:
    def test_extracts_detail_key(self) -> None:
        resp = _mock_response(400, {"detail": "bad request"})
        assert extract_detail(resp) == "bad request"

    def test_extracts_message_key(self) -> None:
        resp = _mock_response(400, {"message": "something wrong"})
        assert extract_detail(resp) == "something wrong"

    def test_returns_none_for_non_dict(self) -> None:
        resp = _mock_response(400, ["not", "a", "dict"])
        assert extract_detail(resp) is None

    def test_returns_none_on_json_error(self) -> None:
        resp = MagicMock(spec=httpx.Response)
        resp.json.side_effect = ValueError("bad json")
        assert extract_detail(resp) is None


class TestHandleResponseError:
    def test_404_exits_4(self) -> None:
        resp = _mock_response(404, {"detail": "not found"})
        with pytest.raises(Exit) as exc_info:
            handle_response_error(resp)
        assert exc_info.value.exit_code == 4

    def test_500_exits_3(self) -> None:
        resp = _mock_response(500, {"detail": "server error"})
        with pytest.raises(Exit) as exc_info:
            handle_response_error(resp)
        assert exc_info.value.exit_code == 3

    def test_500_fk_violation_exits_4(self) -> None:
        """API leaks Postgres FK violations as 500; treat as not-found."""
        fk_msg = 'insert or update on table "story_runs" violates foreign key constraint'
        resp = _mock_response(
            500,
            {"error": "internal_error", "message": fk_msg},
        )
        with pytest.raises(Exit) as exc_info:
            handle_response_error(resp)
        assert exc_info.value.exit_code == 4

    def test_200_does_not_exit(self) -> None:
        resp = _mock_response(200, {"id": "123"})
        handle_response_error(resp)  # Should not raise


class TestFormatRunRow:
    def test_formats_complete_run(self) -> None:
        run = StoryRunResponse.model_validate(_COMPLETED_RUN)
        row = format_run_row(run)
        assert row[0] == _RUN_UUID
        assert row[1] == "Login Story"
        assert row[2] == "completed"
        assert "2025-06-01" in row[3]

    def test_falls_back_to_user_story_id(self) -> None:
        data = {**_PENDING_RUN, "userStoryName": None}
        run = StoryRunResponse.model_validate(data)
        row = format_run_row(run)
        assert row[1] == _USER_STORY_UUID


class TestDisplayRunResult:
    def test_json_mode_outputs_json(self, capsys) -> None:
        run = StoryRunResponse.model_validate(_COMPLETED_RUN)
        display_run_result(run, json_mode=True)
        output = capsys.readouterr().out
        data = json.loads(output)
        assert data["id"] == _RUN_UUID
        assert data["status"] == "completed"
        # model_dump(mode="json") uses Python field names (snake_case)
        assert len(data["results"]) == 2
        assert data["results"][0]["success"] is True
        assert data["results"][1]["fail_reason"] == "Button not found"

    def test_human_mode_shows_criteria_table(self, capsys) -> None:
        run = StoryRunResponse.model_validate(_COMPLETED_RUN)
        display_run_result(run, json_mode=False)
        captured = capsys.readouterr()
        # print_table goes to stdout, per-platform info to stderr
        combined = captured.out + captured.err
        assert _CRITERIA_UUID_1 in combined
        assert "Button not found" in combined


# ---------------------------------------------------------------------------
# start command
# ---------------------------------------------------------------------------


class TestStartCommand:
    def test_start_with_uuid_no_watch_json(self, tmp_path) -> None:
        """Start a run using a user-story UUID, no-watch mode, JSON output."""
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.post = AsyncMock(return_value=_mock_response(200, _PENDING_RUN))

        with patch("minitest_cli.commands.run.ApiClient", return_value=client):
            result = _run_with_context(
                ["start", _USER_STORY_UUID, "--no-watch", *_BUILD_FLAGS],
                settings,
                json_mode=True,
            )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["run_id"] == _RUN_UUID
        assert data["status"] == "pending"

    def test_start_with_name_resolves_user_story(self, tmp_path) -> None:
        """Start a run using a user-story name; verifies list fetch + name resolution."""
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.get = AsyncMock(return_value=_mock_response(200, _USER_STORY_LIST))
        client.post = AsyncMock(return_value=_mock_response(200, _PENDING_RUN))

        with patch("minitest_cli.commands.run.ApiClient", return_value=client):
            result = _run_with_context(
                ["start", "Login Story", "--no-watch", *_BUILD_FLAGS],
                settings,
                json_mode=True,
            )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["run_id"] == _RUN_UUID
        first_get = client.get.call_args_list[0]
        assert "/user-stories" in first_get[0][0]

    def test_start_with_name_case_insensitive(self, tmp_path) -> None:
        """User-story name resolution is case-insensitive."""
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.get = AsyncMock(return_value=_mock_response(200, _USER_STORY_LIST))
        client.post = AsyncMock(return_value=_mock_response(200, _PENDING_RUN))

        with patch("minitest_cli.commands.run.ApiClient", return_value=client):
            result = _run_with_context(
                ["start", "login story", "--no-watch", *_BUILD_FLAGS],
                settings,
                json_mode=True,
            )

        assert result.exit_code == 0

    def test_start_posts_correct_build_ids(self, tmp_path) -> None:
        """Build IDs from flags are sent in the POST body."""
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.post = AsyncMock(return_value=_mock_response(200, _PENDING_RUN))

        with patch("minitest_cli.commands.run.ApiClient", return_value=client):
            result = _run_with_context(
                ["start", _USER_STORY_UUID, "--no-watch", *_BUILD_FLAGS],
                settings,
                json_mode=True,
            )

        assert result.exit_code == 0
        post_call = client.post.call_args
        body = post_call[1]["json"]
        assert body["iosBuildId"] == _IOS_BUILD_UUID
        assert body["androidBuildId"] == _ANDROID_BUILD_UUID

    def test_start_no_watch_human_output(self, tmp_path) -> None:
        """No-watch mode without --json shows human-friendly message."""
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.post = AsyncMock(return_value=_mock_response(200, _PENDING_RUN))

        with patch("minitest_cli.commands.run.ApiClient", return_value=client):
            result = _run_with_context(
                ["start", _USER_STORY_UUID, "--no-watch", *_BUILD_FLAGS],
                settings,
                json_mode=False,
            )

        assert result.exit_code == 0
        assert _RUN_UUID in result.output
        assert "minitest run status" in result.output

    def test_start_user_story_not_found_exits_4(self, tmp_path) -> None:
        """When user-story name doesn't match any known user story, exit code 4."""
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.get = AsyncMock(return_value=_mock_response(200, _USER_STORY_LIST))

        with patch("minitest_cli.commands.run.ApiClient", return_value=client):
            result = _run_with_context(
                ["start", "Nonexistent Story", "--no-watch", *_BUILD_FLAGS],
                settings,
            )

        assert result.exit_code == 4

    def test_start_api_error_exits_3(self, tmp_path) -> None:
        """HTTP 500 from POST /story-runs exits with code 3."""
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.post = AsyncMock(return_value=_mock_response(500, {"detail": "server error"}))

        with patch("minitest_cli.commands.run.ApiClient", return_value=client):
            result = _run_with_context(
                ["start", _USER_STORY_UUID, "--no-watch", *_BUILD_FLAGS],
                settings,
            )

        assert result.exit_code == 3

    def test_start_network_error_exits_3(self, tmp_path) -> None:
        """Network errors (httpx) exit with code 3."""
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))

        with patch("minitest_cli.commands.run.ApiClient", return_value=client):
            result = _run_with_context(
                ["start", _USER_STORY_UUID, "--no-watch", *_BUILD_FLAGS],
                settings,
            )

        assert result.exit_code == 3

    def test_start_requires_auth(self, tmp_path) -> None:
        """Missing auth token exits with code 2."""
        settings = _make_settings(tmp_path, token=None)

        with patch(
            "minitest_cli.core.auth.require_auth",
            side_effect=typer.Exit(code=2),
        ):
            result = _run_with_context(
                ["start", _USER_STORY_UUID, "--no-watch", *_BUILD_FLAGS], settings
            )

        assert result.exit_code == 2

    def test_start_with_watch_polls_and_displays(self, tmp_path) -> None:
        """--watch mode polls until terminal and displays results."""
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.get = AsyncMock(
            side_effect=[
                _mock_response(200, {**_PENDING_RUN, "status": "running"}),
                _mock_response(200, _COMPLETED_RUN),
            ]
        )
        client.post = AsyncMock(return_value=_mock_response(200, _PENDING_RUN))

        with (
            patch("minitest_cli.commands.run.ApiClient", return_value=client),
            patch("minitest_cli.commands.run_helpers.asyncio.sleep", new_callable=AsyncMock),
            patch("minitest_cli.commands.run_helpers.err_console"),
        ):
            result = _run_with_context(
                ["start", _USER_STORY_UUID, *_BUILD_FLAGS],
                settings,
                json_mode=True,
            )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "completed"

    def test_start_requires_both_build_flags(self, tmp_path) -> None:
        """Missing --ios-build or --android-build shows usage error."""
        settings = _make_settings(tmp_path)

        with patch("minitest_cli.commands.run.ApiClient", return_value=_mock_client()):
            result = _run_with_context(
                ["start", _USER_STORY_UUID, "--no-watch"],
                settings,
            )

        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# status command
# ---------------------------------------------------------------------------


class TestStatusCommand:
    def test_status_returns_completed_run(self, tmp_path) -> None:
        """Get status of a completed run in JSON mode."""
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.get = AsyncMock(return_value=_mock_response(200, _COMPLETED_RUN))

        with patch("minitest_cli.commands.run.ApiClient", return_value=client):
            result = _run_with_context(
                ["status", _RUN_UUID],
                settings,
                json_mode=True,
            )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "completed"
        # model_dump(mode="json") uses Python field names (snake_case)
        assert len(data["results"]) == 2
        assert data["results"][0]["success"] is True
        assert data["results"][1]["fail_reason"] == "Button not found"
        # Verify correct endpoint was called
        assert client.get.call_args[0][0] == f"/api/v1/apps/app-123/story-runs/{_RUN_UUID}"

    def test_status_human_mode_shows_results(self, tmp_path) -> None:
        """Human mode displays criteria and recording URLs."""
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.get = AsyncMock(return_value=_mock_response(200, _COMPLETED_RUN))

        with patch("minitest_cli.commands.run.ApiClient", return_value=client):
            result = _run_with_context(
                ["status", _RUN_UUID],
                settings,
                json_mode=False,
            )

        assert result.exit_code == 0
        assert _RUN_UUID in result.output
        assert "Acceptance Criteria" in result.output

    def test_status_404_exits_4(self, tmp_path) -> None:
        """Unknown run ID exits with code 4."""
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.get = AsyncMock(return_value=_mock_response(404, {"detail": "Run not found"}))

        with patch("minitest_cli.commands.run.ApiClient", return_value=client):
            result = _run_with_context(["status", "nonexistent-id"], settings)

        assert result.exit_code == 4

    def test_status_network_error_exits_3(self, tmp_path) -> None:
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))

        with patch("minitest_cli.commands.run.ApiClient", return_value=client):
            result = _run_with_context(["status", _RUN_UUID], settings)

        assert result.exit_code == 3

    def test_status_with_watch_polls_pending(self, tmp_path) -> None:
        """--watch polls a pending run until it reaches terminal status."""
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.get = AsyncMock(
            side_effect=[
                # Initial fetch → running
                _mock_response(200, {**_PENDING_RUN, "status": "running"}),
                # Poll → still running
                _mock_response(200, {**_PENDING_RUN, "status": "running"}),
                # Poll → completed
                _mock_response(200, _COMPLETED_RUN),
            ]
        )

        with (
            patch("minitest_cli.commands.run.ApiClient", return_value=client),
            patch("minitest_cli.commands.run_helpers.asyncio.sleep", new_callable=AsyncMock),
            patch("minitest_cli.commands.run_helpers.err_console"),
        ):
            result = _run_with_context(
                ["status", _RUN_UUID, "--watch"],
                settings,
                json_mode=True,
            )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "completed"

    def test_status_watch_already_terminal_no_poll(self, tmp_path) -> None:
        """--watch on an already-completed run returns immediately without polling."""
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.get = AsyncMock(return_value=_mock_response(200, _COMPLETED_RUN))

        with patch("minitest_cli.commands.run.ApiClient", return_value=client):
            result = _run_with_context(
                ["status", _RUN_UUID, "--watch"],
                settings,
                json_mode=True,
            )

        assert result.exit_code == 0
        # Should only have been called once (no polling loop)
        assert client.get.call_count == 1

    def test_status_requires_auth(self, tmp_path) -> None:
        settings = _make_settings(tmp_path, token=None)

        with patch(
            "minitest_cli.core.auth.require_auth",
            side_effect=typer.Exit(code=2),
        ):
            result = _run_with_context(["status", _RUN_UUID], settings)

        assert result.exit_code == 2

    def test_status_uses_app_flag(self, tmp_path) -> None:
        """App flag overrides settings.app_id."""
        settings = _make_settings(tmp_path, app_id=None)
        client = _mock_client()
        client.get = AsyncMock(return_value=_mock_response(200, _COMPLETED_RUN))

        with patch("minitest_cli.commands.run.ApiClient", return_value=client):
            result = _run_with_context(
                ["status", _RUN_UUID],
                settings,
                json_mode=True,
                app_flag="flag-app-789",
            )

        assert result.exit_code == 0
        assert client.get.call_args[0][0] == f"/api/v1/apps/flag-app-789/story-runs/{_RUN_UUID}"


# ---------------------------------------------------------------------------
# all command
# ---------------------------------------------------------------------------


class TestRunAllCommand:
    def test_all_fires_batch_and_returns_json(self, tmp_path) -> None:
        """run all POST /story-runs/batch, returns JSON list."""
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.post = AsyncMock(return_value=_mock_response(200, _BATCH_RESPONSE))

        with patch("minitest_cli.commands.run.ApiClient", return_value=client):
            result = _run_with_context(
                ["all", *_BUILD_FLAGS],
                settings,
                json_mode=True,
            )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 2
        assert data[0]["run_id"] == _RUN_UUID
        assert data[0]["user_story"] == "Login Story"
        assert client.post.call_args[0][0] == "/api/v1/apps/app-123/story-runs/batch"

    def test_all_human_mode_shows_table(self, tmp_path) -> None:
        """Human mode displays a table of started runs."""
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.post = AsyncMock(return_value=_mock_response(200, _BATCH_RESPONSE))

        with patch("minitest_cli.commands.run.ApiClient", return_value=client):
            result = _run_with_context(
                ["all", *_BUILD_FLAGS],
                settings,
                json_mode=False,
            )

        assert result.exit_code == 0
        assert "Batch Runs" in result.output
        assert "Login Story" in result.output

    def test_all_posts_correct_build_ids(self, tmp_path) -> None:
        """Build IDs from flags are sent in the batch POST body."""
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.post = AsyncMock(return_value=_mock_response(200, _BATCH_RESPONSE))

        with patch("minitest_cli.commands.run.ApiClient", return_value=client):
            result = _run_with_context(
                ["all", *_BUILD_FLAGS],
                settings,
                json_mode=True,
            )

        assert result.exit_code == 0
        post_body = client.post.call_args[1]["json"]
        assert post_body["iosBuildId"] == _IOS_BUILD_UUID
        assert post_body["androidBuildId"] == _ANDROID_BUILD_UUID

    def test_all_api_error_exits_3(self, tmp_path) -> None:
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.post = AsyncMock(return_value=_mock_response(500, {"detail": "error"}))

        with patch("minitest_cli.commands.run.ApiClient", return_value=client):
            result = _run_with_context(["all", *_BUILD_FLAGS], settings)

        assert result.exit_code == 3

    def test_all_network_error_exits_3(self, tmp_path) -> None:
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

        with patch("minitest_cli.commands.run.ApiClient", return_value=client):
            result = _run_with_context(["all", *_BUILD_FLAGS], settings)

        assert result.exit_code == 3

    def test_all_requires_auth(self, tmp_path) -> None:
        settings = _make_settings(tmp_path, token=None)

        with patch(
            "minitest_cli.core.auth.require_auth",
            side_effect=typer.Exit(code=2),
        ):
            result = _run_with_context(["all", *_BUILD_FLAGS], settings)

        assert result.exit_code == 2

    def test_all_requires_both_build_flags(self, tmp_path) -> None:
        """Missing --ios-build or --android-build shows usage error."""
        settings = _make_settings(tmp_path)

        with patch("minitest_cli.commands.run.ApiClient", return_value=_mock_client()):
            result = _run_with_context(["all"], settings)

        assert result.exit_code != 0


class TestListRunsCommand:
    def test_list_json_output(self, tmp_path) -> None:
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.get.return_value = _mock_response(200, _RUN_LIST_RESPONSE)

        with patch("minitest_cli.commands.run.ApiClient", return_value=client):
            result = _run_with_context(["list", _USER_STORY_UUID], settings, json_mode=True)

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data["items"]) == 2

    def test_list_human_output(self, tmp_path) -> None:
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.get.return_value = _mock_response(200, _RUN_LIST_RESPONSE)

        with patch("minitest_cli.commands.run.ApiClient", return_value=client):
            result = _run_with_context(["list", _USER_STORY_UUID], settings)

        assert result.exit_code == 0
        assert "Login Story" in result.output

    def test_list_empty(self, tmp_path) -> None:
        settings = _make_settings(tmp_path)
        client = _mock_client()
        empty = {"items": [], "total": 0, "page": 1, "pageSize": 20}
        client.get.return_value = _mock_response(200, empty)

        with patch("minitest_cli.commands.run.ApiClient", return_value=client):
            result = _run_with_context(["list", _USER_STORY_UUID], settings)

        assert result.exit_code == 0

    def test_list_with_status_filter(self, tmp_path) -> None:
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.get.return_value = _mock_response(200, _RUN_LIST_RESPONSE)

        with patch("minitest_cli.commands.run.ApiClient", return_value=client):
            result = _run_with_context(
                ["list", _USER_STORY_UUID, "--status", "completed"], settings, json_mode=True
            )

        assert result.exit_code == 0
        call_args = client.get.call_args
        assert call_args.kwargs.get("params", {}).get("status") == "completed"

    def test_list_by_name(self, tmp_path) -> None:
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.get.side_effect = [
            _mock_response(200, _USER_STORY_LIST),
            _mock_response(200, _RUN_LIST_RESPONSE),
        ]

        with patch("minitest_cli.commands.run.ApiClient", return_value=client):
            result = _run_with_context(["list", "Login Story"], settings, json_mode=True)

        assert result.exit_code == 0
        path = client.get.call_args_list[1][0][0]
        assert _USER_STORY_UUID in path

    def test_list_api_error(self, tmp_path) -> None:
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.get.return_value = _mock_response(500, {"detail": "Server error"})

        with patch("minitest_cli.commands.run.ApiClient", return_value=client):
            result = _run_with_context(["list", _USER_STORY_UUID], settings)

        assert result.exit_code == 3

    def test_list_network_error(self, tmp_path) -> None:
        settings = _make_settings(tmp_path)
        client = _mock_client()
        client.get.side_effect = httpx.ConnectError("Connection refused")

        with patch("minitest_cli.commands.run.ApiClient", return_value=client):
            result = _run_with_context(["list", _USER_STORY_UUID], settings)

        assert result.exit_code == 3

    def test_list_requires_auth(self, tmp_path) -> None:
        settings = _make_settings(tmp_path, token=None)

        with patch(
            "minitest_cli.core.auth.require_auth",
            side_effect=typer.Exit(code=2),
        ):
            result = _run_with_context(["list", _USER_STORY_UUID], settings)

        assert result.exit_code == 2
