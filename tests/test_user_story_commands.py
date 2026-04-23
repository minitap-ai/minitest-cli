"""Essential tests for user-story commands.

Validates business logic, error handling, and CLI parsing.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import typer
from typer.testing import CliRunner

from minitest_cli.commands.user_story import app as user_story_app
from minitest_cli.core.config import Settings

runner = CliRunner()

VALID_USER_STORY_TYPES = ["login", "registration", "checkout", "onboarding", "other"]


def _make_settings(tmp_path, **overrides):
    defaults = {
        "config_dir": tmp_path,
        "token": "test-token",
        "app_id": "app-123",
        "supabase_url": "https://test.supabase.co",
        "supabase_publishable_key": "test-publishable-key",
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
        result = runner.invoke(user_story_app, args)
    finally:
        for p in patches:
            p.stop()
    return result


def _mock_response(status_code=200, json_data=None):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


SAMPLE_USER_STORY = {
    "id": "story-1",
    "name": "Login Story",
    "type": "login",
    "acceptanceCriteria": [
        {"id": "ac-1", "content": "User can log in"},
        {"id": "ac-2", "content": "Error shown on bad password"},
    ],
}


class TestCreateUserStory:
    def test_invalid_type_rejected(self, tmp_path):
        settings = _make_settings(tmp_path)
        with patch(
            "minitest_cli.commands.user_story_helpers.fetch_user_story_types",
            return_value=VALID_USER_STORY_TYPES,
        ):
            result = _run_with_context(
                ["create", "--name", "Bad Story", "--type", "invalid_type"],
                settings,
            )
        assert result.exit_code != 0
        assert "invalid" in result.output.lower()

    def test_network_error_exits_3(self, tmp_path):
        settings = _make_settings(tmp_path)
        with (
            patch(
                "minitest_cli.commands.user_story_helpers.fetch_user_story_types",
                return_value=VALID_USER_STORY_TYPES,
            ),
            patch("minitest_cli.commands.user_story.ApiClient") as MockClient,
        ):
            instance = AsyncMock()
            instance.post.side_effect = httpx.ConnectError("Connection refused")
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            result = _run_with_context(
                ["create", "--name", "Story", "--type", "login"],
                settings,
            )
        assert result.exit_code == 3
        assert "network error" in result.output.lower() or "error" in result.output.lower()

    def test_valid_type_accepted(self, tmp_path):
        settings = _make_settings(tmp_path)
        mock_resp = _mock_response(201, {"id": "new-story", "name": "Story", "type": "login"})
        with (
            patch(
                "minitest_cli.commands.user_story_helpers.fetch_user_story_types",
                return_value=VALID_USER_STORY_TYPES,
            ),
            patch("minitest_cli.commands.user_story.ApiClient") as MockClient,
        ):
            instance = AsyncMock()
            instance.post.return_value = mock_resp
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            result = _run_with_context(
                ["create", "--name", "Story", "--type", "login"],
                settings,
            )
        assert result.exit_code == 0


class TestListUserStories:
    def test_invalid_type_rejected(self, tmp_path):
        settings = _make_settings(tmp_path)
        with patch(
            "minitest_cli.commands.user_story_helpers.fetch_user_story_types",
            return_value=VALID_USER_STORY_TYPES,
        ):
            result = _run_with_context(["list", "--type", "bad_type"], settings)
        assert result.exit_code != 0
        assert "bad_type" in result.output.lower() or "invalid" in result.output.lower()

    def test_all_flag_fetches_multiple_pages(self, tmp_path):
        settings = _make_settings(tmp_path)
        page1_resp = _mock_response(
            200, {"items": [SAMPLE_USER_STORY], "total": 2, "page": 1, "pageSize": 100}
        )
        page2_resp = _mock_response(
            200, {"items": [SAMPLE_USER_STORY], "total": 2, "page": 2, "pageSize": 100}
        )
        with patch("minitest_cli.commands.user_story.ApiClient") as MockClient:
            instance = AsyncMock()
            instance.get.side_effect = [page1_resp, page2_resp]
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            result = _run_with_context(["list", "--all"], settings, json_mode=True)
        assert result.exit_code == 0
        assert instance.get.call_count == 2
        data = json.loads(result.output)
        assert len(data) == 2


class TestGetUserStory:
    def test_not_found_exits_4(self, tmp_path):
        settings = _make_settings(tmp_path)
        mock_resp = _mock_response(404, {"detail": "User story not found"})
        with patch("minitest_cli.commands.user_story.ApiClient") as MockClient:
            instance = AsyncMock()
            instance.get.return_value = mock_resp
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            result = _run_with_context(["get", "story-1"], settings)
        assert result.exit_code == 4
        assert "not found" in result.output.lower()


class TestUpdateUserStory:
    def test_add_criteria_fetches_and_appends(self, tmp_path):
        settings = _make_settings(tmp_path)
        get_resp = _mock_response(200, SAMPLE_USER_STORY)
        patch_resp = _mock_response(200, SAMPLE_USER_STORY)
        with patch("minitest_cli.commands.user_story_modify.ApiClient") as MockClient:
            instance = AsyncMock()
            instance.get.return_value = get_resp
            instance.patch.return_value = patch_resp
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            result = _run_with_context(
                ["update", "story-1", "--add-criteria", "New criterion"],
                settings,
                json_mode=True,
            )
        assert result.exit_code == 0
        instance.get.assert_called_once()
        call_kwargs = instance.patch.call_args
        payload = call_kwargs.kwargs["json"]
        criteria = payload.get("acceptanceCriteria") or payload.get("acceptance_criteria")
        contents = [c.get("content") for c in criteria]
        assert "User can log in" in contents
        assert "Error shown on bad password" in contents
        assert "New criterion" in contents

    def test_replace_criteria_preserves_ids_for_unchanged_content(self, tmp_path):
        """--criteria replace must reuse the stable criterionId for any entry
        whose content already exists on the story; only brand-new contents are
        sent without an id. Previously the CLI sent everything as new which
        destroyed criterion identity on every replace."""
        settings = _make_settings(tmp_path)
        story = {
            "id": "story-1",
            "name": "Login",
            "type": "login",
            "acceptanceCriteria": [
                {"id": "v-1", "criterionId": "crit-alpha", "content": "alpha"},
                {"id": "v-2", "criterionId": "crit-beta", "content": "beta"},
            ],
        }
        get_resp = _mock_response(200, story)
        patch_resp = _mock_response(200, story)
        with patch("minitest_cli.commands.user_story_modify.ApiClient") as MockClient:
            instance = AsyncMock()
            instance.get.return_value = get_resp
            instance.patch.return_value = patch_resp
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            result = _run_with_context(
                [
                    "update",
                    "story-1",
                    "--criteria",
                    "alpha",
                    "--criteria",
                    "gamma",
                ],
                settings,
                json_mode=True,
            )
        assert result.exit_code == 0
        payload = instance.patch.call_args.kwargs["json"]
        sent = payload["acceptanceCriteria"]
        assert {"id": "crit-alpha", "content": "alpha"} in sent
        # gamma is new → no id so backend creates a new criterion
        assert {"content": "gamma"} in sent
        assert len(sent) == 2

    def test_replace_criteria_without_match_sends_no_id(self, tmp_path):
        """If no existing criterion has the same content, the entry must be
        sent with ``content`` only so the backend creates a fresh criterion."""
        settings = _make_settings(tmp_path)
        story = {
            "id": "story-1",
            "name": "Login",
            "type": "login",
            "acceptanceCriteria": [
                {"id": "v-1", "criterionId": "crit-alpha", "content": "alpha"},
            ],
        }
        get_resp = _mock_response(200, story)
        patch_resp = _mock_response(200, story)
        with patch("minitest_cli.commands.user_story_modify.ApiClient") as MockClient:
            instance = AsyncMock()
            instance.get.return_value = get_resp
            instance.patch.return_value = patch_resp
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            result = _run_with_context(
                ["update", "story-1", "--criteria", "totally new"],
                settings,
                json_mode=True,
            )
        assert result.exit_code == 0
        payload = instance.patch.call_args.kwargs["json"]
        assert payload["acceptanceCriteria"] == [{"content": "totally new"}]

    def test_replace_criteria_duplicate_content_does_not_reuse_id(self, tmp_path):
        """If the user passes the same content twice via --criteria, each
        occurrence must consume at most one existing id. Reusing the same id
        twice would trip the backend's duplicate-id guard."""
        settings = _make_settings(tmp_path)
        story = {
            "id": "story-1",
            "name": "Login",
            "type": "login",
            "acceptanceCriteria": [
                {"id": "v-1", "criterionId": "crit-alpha", "content": "alpha"},
            ],
        }
        get_resp = _mock_response(200, story)
        patch_resp = _mock_response(200, story)
        with patch("minitest_cli.commands.user_story_modify.ApiClient") as MockClient:
            instance = AsyncMock()
            instance.get.return_value = get_resp
            instance.patch.return_value = patch_resp
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            result = _run_with_context(
                [
                    "update",
                    "story-1",
                    "--criteria",
                    "alpha",
                    "--criteria",
                    "alpha",
                ],
                settings,
                json_mode=True,
            )
        assert result.exit_code == 0
        sent = instance.patch.call_args.kwargs["json"]["acceptanceCriteria"]
        ids = [c.get("id") for c in sent]
        assert ids.count("crit-alpha") <= 1
        # First occurrence consumes the existing id; second is sent as brand-new.
        assert sent == [
            {"id": "crit-alpha", "content": "alpha"},
            {"content": "alpha"},
        ]

    def test_empty_payload_rejected(self, tmp_path):
        settings = _make_settings(tmp_path)
        result = _run_with_context(["update", "story-1"], settings)
        assert result.exit_code == 1
        assert "Provide at least one field to update" in result.output

    def test_conflicting_criteria_flags_rejected(self, tmp_path):
        settings = _make_settings(tmp_path)
        result = _run_with_context(
            ["update", "story-1", "--criteria", "A", "--add-criteria", "B"],
            settings,
        )
        assert result.exit_code == 1
        assert "Use either --criteria or --add-criteria, not both" in result.output

    def test_invalid_type_rejected(self, tmp_path):
        settings = _make_settings(tmp_path)
        with patch(
            "minitest_cli.commands.user_story_helpers.fetch_user_story_types",
            return_value=VALID_USER_STORY_TYPES,
        ):
            result = _run_with_context(
                ["update", "story-1", "--type", "nonsense"],
                settings,
            )
        assert result.exit_code != 0
        assert "invalid" in result.output.lower() or "nonsense" in result.output.lower()


class TestDeleteUserStory:
    def test_requires_force_flag(self, tmp_path):
        settings = _make_settings(tmp_path)
        result = _run_with_context(["delete", "story-1"], settings)
        assert result.exit_code == 1
        assert "--force" in result.output

    def test_not_found_exits_4(self, tmp_path):
        settings = _make_settings(tmp_path)
        mock_resp = _mock_response(404, {"detail": "User story not found"})
        with patch("minitest_cli.commands.user_story_modify.ApiClient") as MockClient:
            instance = AsyncMock()
            instance.delete.return_value = mock_resp
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            result = _run_with_context(["delete", "story-1", "--force"], settings)
        assert result.exit_code == 4
        assert "not found" in result.output.lower()


class TestFetchUserStoryTypes:
    """Tests for the fetch_user_story_types helper."""

    def test_returns_api_types_on_success(self, tmp_path):
        from minitest_cli.commands.user_story_helpers import fetch_user_story_types

        settings = _make_settings(tmp_path)
        api_types = ["login", "registration", "checkout", "new_type"]
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = api_types
        with patch("minitest_cli.commands.user_story_helpers.httpx.get", return_value=mock_resp):
            result = fetch_user_story_types(settings)
        assert result == api_types

    def test_network_error_exits_3(self, tmp_path):
        from click.exceptions import Exit

        from minitest_cli.commands.user_story_helpers import fetch_user_story_types

        settings = _make_settings(tmp_path)
        with (
            patch(
                "minitest_cli.commands.user_story_helpers.httpx.get",
                side_effect=httpx.ConnectError("fail"),
            ),
            pytest.raises(Exit) as exc_info,
        ):
            fetch_user_story_types(settings)
        assert exc_info.value.exit_code == 3

    def test_non_200_exits_3(self, tmp_path):
        from click.exceptions import Exit

        from minitest_cli.commands.user_story_helpers import fetch_user_story_types

        settings = _make_settings(tmp_path)
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 500
        with (
            patch("minitest_cli.commands.user_story_helpers.httpx.get", return_value=mock_resp),
            pytest.raises(Exit) as exc_info,
        ):
            fetch_user_story_types(settings)
        assert exc_info.value.exit_code == 3
