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


SAMPLE_STORY_WITH_DEPS = {
    "id": "story-1",
    "name": "Checkout",
    "type": "checkout",
    "appId": "app-123",
    "createdAt": "2026-04-28T00:00:00Z",
    "dependsOn": ["story-login", "story-onboarding"],
    "acceptanceCriteria": [{"id": "ac-1", "content": "User can checkout"}],
}


class TestCreateUserStoryDependsOn:
    """``create --depends-on`` does a POST then a PATCH so the agent gets
    create + dep declaration in a single CLI call."""

    def test_create_with_depends_on_sends_followup_patch(self, tmp_path):
        settings = _make_settings(tmp_path)
        post_resp = _mock_response(201, {"id": "story-new", "name": "Checkout", "type": "checkout"})
        patch_resp = _mock_response(200, SAMPLE_STORY_WITH_DEPS)
        with (
            patch(
                "minitest_cli.commands.user_story_helpers.fetch_user_story_types",
                return_value=VALID_USER_STORY_TYPES,
            ),
            patch("minitest_cli.commands.user_story.ApiClient") as MockClient,
        ):
            instance = AsyncMock()
            instance.post.return_value = post_resp
            instance.patch.return_value = patch_resp
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            result = _run_with_context(
                [
                    "create",
                    "--name",
                    "Checkout",
                    "--type",
                    "checkout",
                    "--depends-on",
                    "story-login",
                    "--depends-on",
                    "story-onboarding",
                ],
                settings,
                json_mode=True,
            )
        assert result.exit_code == 0
        # POST has the create payload, PATCH carries dependsOn replace.
        instance.post.assert_called_once()
        instance.patch.assert_called_once()
        patch_payload = instance.patch.call_args.kwargs["json"]
        assert patch_payload == {"dependsOn": ["story-login", "story-onboarding"]}

    def test_create_without_depends_on_skips_patch(self, tmp_path):
        settings = _make_settings(tmp_path)
        post_resp = _mock_response(201, {"id": "story-new", "name": "S", "type": "login"})
        with (
            patch(
                "minitest_cli.commands.user_story_helpers.fetch_user_story_types",
                return_value=VALID_USER_STORY_TYPES,
            ),
            patch("minitest_cli.commands.user_story.ApiClient") as MockClient,
        ):
            instance = AsyncMock()
            instance.post.return_value = post_resp
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            result = _run_with_context(
                ["create", "--name", "S", "--type", "login"],
                settings,
                json_mode=True,
            )
        assert result.exit_code == 0
        instance.patch.assert_not_called()


class TestUpdateDependsOn:
    """``update --depends-on`` is a full-set replace; ``--remove-dependency`` is a
    surgical delta that requires fetching the current story to subtract from."""

    def test_depends_on_replaces_full_set(self, tmp_path):
        settings = _make_settings(tmp_path)
        patch_resp = _mock_response(200, SAMPLE_STORY_WITH_DEPS)
        with patch("minitest_cli.commands.user_story_modify.ApiClient") as MockClient:
            instance = AsyncMock()
            instance.patch.return_value = patch_resp
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            result = _run_with_context(
                ["update", "story-1", "--depends-on", "p1", "--depends-on", "p2"],
                settings,
                json_mode=True,
            )
        assert result.exit_code == 0
        # Pure replace path: no GET needed because the user passed the
        # full desired set explicitly.
        instance.get.assert_not_called()
        payload = instance.patch.call_args.kwargs["json"]
        assert payload["dependsOn"] == ["p1", "p2"]

    def test_remove_dependency_subtracts_from_current(self, tmp_path):
        settings = _make_settings(tmp_path)
        get_resp = _mock_response(
            200,
            {
                "id": "story-1",
                "name": "Checkout",
                "type": "checkout",
                "dependsOn": ["story-login", "story-onboarding", "story-extra"],
            },
        )
        patch_resp = _mock_response(200, SAMPLE_STORY_WITH_DEPS)
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
                    "--remove-dependency",
                    "story-extra",
                    "--remove-dependency",
                    "story-onboarding",
                ],
                settings,
                json_mode=True,
            )
        assert result.exit_code == 0
        # Delta needs the current set, then PATCHes with the survivors.
        instance.get.assert_called_once()
        payload = instance.patch.call_args.kwargs["json"]
        assert payload["dependsOn"] == ["story-login"]

    def test_remove_dependency_with_unknown_id_is_a_noop(self, tmp_path):
        # Removing an id that isn't in the current set leaves the set
        # unchanged — we still PATCH with the full set, which is a no-op
        # on the server.
        settings = _make_settings(tmp_path)
        get_resp = _mock_response(
            200,
            {
                "id": "story-1",
                "name": "Checkout",
                "type": "checkout",
                "dependsOn": ["a", "b"],
            },
        )
        patch_resp = _mock_response(200, SAMPLE_STORY_WITH_DEPS)
        with patch("minitest_cli.commands.user_story_modify.ApiClient") as MockClient:
            instance = AsyncMock()
            instance.get.return_value = get_resp
            instance.patch.return_value = patch_resp
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            result = _run_with_context(
                ["update", "story-1", "--remove-dependency", "not-there"],
                settings,
                json_mode=True,
            )
        assert result.exit_code == 0
        payload = instance.patch.call_args.kwargs["json"]
        assert payload["dependsOn"] == ["a", "b"]

    def test_depends_on_wins_over_remove_dependency(self, tmp_path):
        # Both flags present: replace wins, delta is silently dropped after a
        # warning. The PATCH must carry only the replace set, not a subtraction.
        settings = _make_settings(tmp_path)
        patch_resp = _mock_response(200, SAMPLE_STORY_WITH_DEPS)
        with patch("minitest_cli.commands.user_story_modify.ApiClient") as MockClient:
            instance = AsyncMock()
            instance.patch.return_value = patch_resp
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            result = _run_with_context(
                [
                    "update",
                    "story-1",
                    "--depends-on",
                    "p1",
                    "--remove-dependency",
                    "p1",
                ],
                settings,
                json_mode=True,
            )
        assert result.exit_code == 0
        instance.get.assert_not_called()
        assert "--remove-dependency ignored" in result.output
        payload = instance.patch.call_args.kwargs["json"]
        assert payload["dependsOn"] == ["p1"]

    def test_dependency_validation_422_surfaces_kind_and_ids(self, tmp_path):
        # The testing-service emits a structured 422 detail with kind+ids; the
        # CLI must render it instead of a generic "API error" so the user
        # sees which rule broke and on which IDs.
        settings = _make_settings(tmp_path)
        validation_resp = _mock_response(
            422,
            {
                "detail": {
                    "kind": "cycle",
                    "message": "depends_on would create a cycle",
                    "ids": ["a", "b", "a"],
                }
            },
        )
        with patch("minitest_cli.commands.user_story_modify.ApiClient") as MockClient:
            instance = AsyncMock()
            instance.patch.return_value = validation_resp
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            result = _run_with_context(
                ["update", "story-1", "--depends-on", "a"],
                settings,
            )
        assert result.exit_code == 3
        assert "cycle" in result.output.lower()
        assert "a, b, a" in result.output


class TestSuggestDepsCommand:
    """Tests for ``user-story suggest-deps``."""

    def test_empty_response_prints_hint(self, tmp_path):
        settings = _make_settings(tmp_path)
        empty_resp = _mock_response(200, {"suggestions": []})
        with patch("minitest_cli.commands.user_story.ApiClient") as MockClient:
            instance = AsyncMock()
            instance.post.return_value = empty_resp
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            result = _run_with_context(["suggest-deps"], settings)
        assert result.exit_code == 0
        # Hint nudges the user toward the direct path when there's nothing to apply.
        assert "depends-on" in result.output.lower() or "no dependencies" in result.output.lower()

    def test_yes_flag_applies_grouped_per_child(self, tmp_path):
        # Two suggestions for the same child must collapse into one PATCH —
        # the spec calls this out as the avoid-N-PATCHes optimisation.
        settings = _make_settings(tmp_path)
        suggest_resp = _mock_response(
            200,
            {
                "suggestions": [
                    {
                        "userStoryId": "child",
                        "dependsOnUserStoryId": "parent-a",
                        "confidence": 0.9,
                        "reasoning": "needs a",
                    },
                    {
                        "userStoryId": "child",
                        "dependsOnUserStoryId": "parent-b",
                        "confidence": 0.8,
                        "reasoning": "needs b",
                    },
                ]
            },
        )
        list_resp = _mock_response(
            200,
            {
                "items": [
                    {
                        "id": "child",
                        "name": "Child",
                        "type": "checkout",
                        "appId": "app-123",
                        "createdAt": "2026-04-28T00:00:00Z",
                    },
                    {
                        "id": "parent-a",
                        "name": "ParentA",
                        "type": "login",
                        "appId": "app-123",
                        "createdAt": "2026-04-28T00:00:00Z",
                    },
                    {
                        "id": "parent-b",
                        "name": "ParentB",
                        "type": "onboarding",
                        "appId": "app-123",
                        "createdAt": "2026-04-28T00:00:00Z",
                    },
                ],
                "total": 3,
                "page": 1,
                "pageSize": 100,
            },
        )
        get_child = _mock_response(
            200,
            {
                "id": "child",
                "name": "Child",
                "type": "checkout",
                "dependsOn": [],
            },
        )
        patch_child = _mock_response(200, {"id": "child", "dependsOn": ["parent-a", "parent-b"]})
        with patch("minitest_cli.commands.user_story.ApiClient") as MockClient:
            instance = AsyncMock()
            instance.post.return_value = suggest_resp
            instance.get.side_effect = [list_resp, get_child]
            instance.patch.return_value = patch_child
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            result = _run_with_context(
                ["suggest-deps", "--yes"],
                settings,
                json_mode=True,
            )
        assert result.exit_code == 0
        # One PATCH for the single child, carrying both parents merged with
        # whatever was already there (empty here).
        assert instance.patch.call_count == 1
        sent = instance.patch.call_args.kwargs["json"]
        assert set(sent["dependsOn"]) == {"parent-a", "parent-b"}

    def test_yes_flag_unions_with_existing_deps(self, tmp_path):
        # If the child already has deps wired up via the webapp, accepting a new
        # suggestion must not clobber them — the PATCH sends the union.
        settings = _make_settings(tmp_path)
        suggest_resp = _mock_response(
            200,
            {
                "suggestions": [
                    {
                        "userStoryId": "child",
                        "dependsOnUserStoryId": "parent-new",
                        "confidence": 0.9,
                        "reasoning": "fresh suggestion",
                    },
                ]
            },
        )
        list_resp = _mock_response(
            200,
            {
                "items": [
                    {
                        "id": "child",
                        "name": "Child",
                        "type": "checkout",
                        "appId": "app-123",
                        "createdAt": "2026-04-28T00:00:00Z",
                    },
                    {
                        "id": "parent-new",
                        "name": "ParentNew",
                        "type": "login",
                        "appId": "app-123",
                        "createdAt": "2026-04-28T00:00:00Z",
                    },
                ],
                "total": 2,
                "page": 1,
                "pageSize": 100,
            },
        )
        get_child = _mock_response(
            200,
            {
                "id": "child",
                "name": "Child",
                "type": "checkout",
                "dependsOn": ["parent-existing"],
            },
        )
        patch_child = _mock_response(
            200, {"id": "child", "dependsOn": ["parent-existing", "parent-new"]}
        )
        with patch("minitest_cli.commands.user_story.ApiClient") as MockClient:
            instance = AsyncMock()
            instance.post.return_value = suggest_resp
            instance.get.side_effect = [list_resp, get_child]
            instance.patch.return_value = patch_child
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            result = _run_with_context(
                ["suggest-deps", "--yes"],
                settings,
                json_mode=True,
            )
        assert result.exit_code == 0
        sent = instance.patch.call_args.kwargs["json"]
        assert set(sent["dependsOn"]) == {"parent-existing", "parent-new"}

    def test_non_tty_without_yes_errors(self, tmp_path):
        # CliRunner is non-TTY. Without --yes the command must fail loudly
        # instead of hanging on typer.confirm.
        settings = _make_settings(tmp_path)
        suggest_resp = _mock_response(
            200,
            {
                "suggestions": [
                    {
                        "userStoryId": "child",
                        "dependsOnUserStoryId": "parent-a",
                        "confidence": 0.9,
                        "reasoning": "x",
                    }
                ]
            },
        )
        list_resp = _mock_response(
            200,
            {
                "items": [],
                "total": 0,
                "page": 1,
                "pageSize": 100,
            },
        )
        with patch("minitest_cli.commands.user_story.ApiClient") as MockClient:
            instance = AsyncMock()
            instance.post.return_value = suggest_resp
            instance.get.return_value = list_resp
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            result = _run_with_context(["suggest-deps"], settings)
        assert result.exit_code == 1
        assert "--yes" in result.output


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
