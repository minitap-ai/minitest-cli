"""The in-app purchase flag on scenarios, driven against a fake testing-service API."""

import json
from typing import Any

import httpx
from click import unstyle
from typer.testing import CliRunner

from minitest_cli.commands import user_story
from tests._commit_transport import cli_context, make_settings, routed

runner = CliRunner()

APP = "a0d9820f-5136-4f70-b46b-e5966f56bfb5"
STORIES = f"/api/v1/apps/{APP}/user-stories"


class FakeStories:
    """Stores scenarios like testing-service, which drops the flag when the feature is off."""

    def __init__(self, *, feature_enabled: bool = True) -> None:
        self.feature_enabled = feature_enabled
        self.stories: dict[str, dict[str, Any]] = {}
        self.patches: list[dict[str, Any]] = []

    def _apply(self, story: dict[str, Any], body: dict[str, Any]) -> None:
        if "requiresInAppPurchases" in body:
            story["requiresInAppPurchases"] = (
                body["requiresInAppPurchases"] and self.feature_enabled
            )

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path, method = request.url.path, request.method
        if path == STORIES and method == "POST":
            body = json.loads(request.content)
            story = {"id": f"story-{len(self.stories) + 1}", "appId": APP, "name": body["name"]}
            story["requiresInAppPurchases"] = False
            self._apply(story, body)
            self.stories[story["id"]] = story
            return httpx.Response(201, json=story)
        if path == STORIES and method == "GET":
            items = list(self.stories.values())
            return httpx.Response(
                200, json={"items": items, "total": len(items), "page": 1, "pageSize": 20}
            )
        story = self.stories[path.rsplit("/", 1)[-1]]
        if method == "PATCH":
            body = json.loads(request.content)
            self.patches.append(body)
            self._apply(story, body)
        return httpx.Response(200, json=story)


def _invoke(tmp_path, backend: FakeStories, args: list[str], *, json_mode: bool = False):
    with cli_context(make_settings(tmp_path), json_mode=json_mode), routed(backend):
        result = runner.invoke(user_story.app, args)
    return result, unstyle(result.output)


class TestInAppPurchasesFlag:
    def test_create_flagged_scenario_shows_it_in_get_and_list(self, tmp_path):
        backend = FakeStories()

        result, out = _invoke(tmp_path, backend, ["create", "--name", "Buy", "--in-app-purchases"])
        _invoke(tmp_path, backend, ["create", "--name", "Browse"])

        assert result.exit_code == 0
        assert "In-app purchases: on" in out
        _, shown = _invoke(tmp_path, backend, ["get", "story-1"])
        assert "In-app purchases: on" in shown
        _, listed = _invoke(tmp_path, backend, ["list"])
        buy_row, browse_row = [line for line in listed.splitlines() if "story-" in line]
        assert "IAP" in listed
        assert "yes" in buy_row and "yes" not in browse_row
        _, as_json = _invoke(tmp_path, backend, ["get", "story-1"], json_mode=True)
        assert json.loads(as_json)["requiresInAppPurchases"] is True

    def test_update_turns_flag_off_and_leaves_it_alone_when_omitted(self, tmp_path):
        backend = FakeStories()
        _invoke(tmp_path, backend, ["create", "--name", "Buy", "--in-app-purchases"])

        _invoke(tmp_path, backend, ["update", "story-1", "--name", "Buy pro"])
        assert backend.stories["story-1"]["requiresInAppPurchases"] is True

        result, out = _invoke(tmp_path, backend, ["update", "story-1", "--no-in-app-purchases"])

        assert result.exit_code == 0
        assert backend.patches[-1] == {"requiresInAppPurchases": False}
        assert backend.stories["story-1"]["requiresInAppPurchases"] is False
        assert "In-app purchases: off" in out

    def test_warns_when_workspace_ignores_the_flag(self, tmp_path):
        backend = FakeStories(feature_enabled=False)

        result, out = _invoke(tmp_path, backend, ["create", "--name", "Buy", "--in-app-purchases"])

        assert result.exit_code == 0
        assert "not enabled for this workspace" in out
        assert backend.stories["story-1"]["requiresInAppPurchases"] is False
