"""Tags across the CLI, driven against an in-memory fake of the testing-service API."""

import json
from typing import Any

import httpx
from typer.testing import CliRunner

from minitest_cli.commands import flow_types, run, tags, user_story
from tests._commit_transport import cli_context, make_settings, routed

runner = CliRunner()

APP = "a0d9820f-5136-4f70-b46b-e5966f56bfb5"
TAGS = f"/api/v1/apps/{APP}/tags"
STORIES = f"/api/v1/apps/{APP}/user-stories"
BATCHES = f"/api/v1/apps/{APP}/batches"


def _tag(tag_id: str, name: str, count: int = 0) -> dict[str, Any]:
    return {
        "id": tag_id,
        "name": name,
        "color": "gray",
        "description": None,
        "scenarioCount": count,
    }


def _story(story_id: str, name: str, *tags: dict[str, Any]) -> dict[str, Any]:
    refs = [{"id": t["id"], "name": t["name"], "color": t["color"]} for t in tags]
    return {"id": story_id, "appId": APP, "name": name, "type": "other", "tags": refs}


CHECKOUT = _tag("tag-checkout", "Checkout", 2)
SMOKE = _tag("tag-smoke", "smoke", 1)
LOGIN_STORY = _story("story-login", "Log in", SMOKE)
PAY_STORY = _story("story-pay", "Pay by card", CHECKOUT)
REFUND_STORY = _story("story-refund", "Refund", CHECKOUT, SMOKE)
ALL_STORIES = [LOGIN_STORY, PAY_STORY, REFUND_STORY]


class FakeBackend:
    def __init__(self) -> None:
        self.tags = [CHECKOUT, SMOKE]
        self.requests: list[httpx.Request] = []

    def sent(self, method: str, path: str) -> list[httpx.Request]:
        return [r for r in self.requests if r.method == method and r.url.path == path]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path, method = request.url.path, request.method
        if path == TAGS and method == "GET":
            return httpx.Response(200, json=self.tags)
        if path == TAGS and method == "POST":
            name = json.loads(request.content)["name"]
            existing = [t for t in self.tags if t["name"].lower() == name.lower()]
            if existing:
                return httpx.Response(200, json=existing[0])
            return httpx.Response(201, json=_tag("tag-new", name))
        if path.startswith(f"{TAGS}/") and method == "PATCH":
            body = json.loads(request.content)
            if body.get("name", "").lower() == "smoke":
                return httpx.Response(409, json={"detail": "A tag named smoke already exists."})
            return httpx.Response(200, json={**CHECKOUT, **body})
        if path.startswith(f"{TAGS}/") and method == "DELETE":
            return httpx.Response(204)
        if path == STORIES and method == "GET":
            wanted = set(request.url.params.get_list("tagId"))
            items = [s for s in ALL_STORIES if not wanted or {t["id"] for t in s["tags"]} & wanted]
            return httpx.Response(
                200, json={"items": items, "total": len(items), "page": 1, "pageSize": 100}
            )
        if path == STORIES and method == "POST":
            body = json.loads(request.content)
            return httpx.Response(201, json={**_story("story-new", body["name"]), **body})
        if path.startswith(f"{STORIES}/") and method == "PATCH":
            return httpx.Response(200, json=LOGIN_STORY)
        if path == BATCHES and method == "POST":
            ids = json.loads(request.content)["userStoryIds"]
            runs = [
                {"id": f"run-{i}", "userStoryId": i, "createdAt": "2026-10-06T00:00:00Z"}
                for i in ids
            ]
            return httpx.Response(
                201,
                json={
                    "id": "batch-1",
                    "appId": APP,
                    "tenantId": "tenant-1",
                    "source": "cli",
                    "status": "pending",
                    "createdAt": "2026-10-06T00:00:00Z",
                    "storyRuns": runs,
                },
            )
        return httpx.Response(500, json={"detail": f"unexpected {method} {path}"})


GROUPS = {"tags": tags.app, "user-story": user_story.app, "run": run.app}
GROUPS["flow-types"] = flow_types.app


def _invoke(tmp_path, backend: FakeBackend, args: list[str], *, json_mode: bool = False):
    group, *rest = args
    with cli_context(make_settings(tmp_path), json_mode=json_mode), routed(backend):
        return runner.invoke(GROUPS[group], rest)


class TestTagsCommands:
    def test_list_shows_each_tag_with_its_scenario_count(self, tmp_path):
        result = _invoke(tmp_path, FakeBackend(), ["tags", "list"])

        assert result.exit_code == 0, result.output
        assert "Checkout" in result.stdout
        assert "smoke" in result.stdout
        assert "2" in result.stdout

    def test_create_reports_whether_the_tag_is_new(self, tmp_path):
        backend = FakeBackend()

        created = _invoke(
            tmp_path, backend, ["tags", "create", "--name", "Payments", "--color", "amber"]
        )
        reused = _invoke(tmp_path, backend, ["tags", "create", "--name", "CHECKOUT"])

        assert created.exit_code == 0, created.output
        assert json.loads(backend.sent("POST", TAGS)[0].content) == {
            "name": "Payments",
            "color": "amber",
        }
        assert "Tag created: Payments" in created.stderr
        assert "Tag already exists: Checkout" in reused.stderr

    def test_create_rejects_a_colour_outside_the_palette(self, tmp_path):
        backend = FakeBackend()

        result = _invoke(tmp_path, backend, ["tags", "create", "--name", "x", "--color", "lime"])

        assert result.exit_code == 2
        assert backend.requests == []

    def test_update_resolves_the_tag_by_name_case_insensitively(self, tmp_path):
        backend = FakeBackend()

        result = _invoke(
            tmp_path, backend, ["tags", "update", "checkout", "--name", "Payment"], json_mode=True
        )

        assert result.exit_code == 0, result.output
        assert json.loads(backend.sent("PATCH", f"{TAGS}/tag-checkout")[0].content) == {
            "name": "Payment"
        }
        assert json.loads(result.stdout)["name"] == "Payment"

    def test_update_surfaces_a_rename_collision(self, tmp_path):
        result = _invoke(tmp_path, FakeBackend(), ["tags", "update", "Checkout", "--name", "Smoke"])

        assert result.exit_code == 3
        assert "already exists" in result.stderr

    def test_update_unknown_tag_exits_4_listing_known_tags(self, tmp_path):
        result = _invoke(tmp_path, FakeBackend(), ["tags", "update", "nope", "--color", "red"])

        assert result.exit_code == 4
        assert "Known tags: Checkout, smoke" in result.stderr

    def test_delete_requires_yes_then_deletes_by_name(self, tmp_path):
        backend = FakeBackend()

        refused = _invoke(tmp_path, backend, ["tags", "delete", "smoke"])
        assert refused.exit_code == 1
        assert backend.requests == []

        deleted = _invoke(tmp_path, backend, ["tags", "delete", "smoke", "--yes"])
        assert deleted.exit_code == 0, deleted.output
        assert len(backend.sent("DELETE", f"{TAGS}/tag-smoke")) == 1

    def test_flow_types_still_works_but_warns(self, tmp_path):
        backend = FakeBackend()

        result = _invoke(tmp_path, backend, ["flow-types", "create", "--name", "x"])

        assert "`minitest flow-types` is deprecated" in result.stderr
        assert backend.sent("POST", f"/api/v1/apps/{APP}/custom-user-story-types")


class TestUserStoryTags:
    def test_create_sends_tag_names_and_maps_deprecated_type(self, tmp_path):
        backend = FakeBackend()

        result = _invoke(
            tmp_path,
            backend,
            ["user-story", "create", "--name", "Refund", "--tag", "smoke", "--type", "Checkout"],
        )

        assert result.exit_code == 0, result.output
        assert json.loads(backend.sent("POST", STORIES)[0].content) == {
            "name": "Refund",
            "tags": ["smoke", "Checkout"],
        }
        assert "--type is deprecated; use --tag instead." in result.stderr

    def test_update_replaces_tags(self, tmp_path):
        backend = FakeBackend()

        result = _invoke(
            tmp_path,
            backend,
            ["user-story", "update", "story-login", "--tag", "smoke", "--tag", "Smoke"],
        )

        assert result.exit_code == 0, result.output
        patch = backend.sent("PATCH", f"{STORIES}/story-login")[0]
        assert json.loads(patch.content) == {"tags": ["smoke"]}

    def test_clear_tags_sends_an_empty_set(self, tmp_path):
        backend = FakeBackend()

        result = _invoke(tmp_path, backend, ["user-story", "update", "story-login", "--clear-tags"])

        assert result.exit_code == 0, result.output
        patch = backend.sent("PATCH", f"{STORIES}/story-login")[0]
        assert json.loads(patch.content) == {"tags": []}

    def test_clear_tags_with_tag_is_rejected(self, tmp_path):
        backend = FakeBackend()

        result = _invoke(
            tmp_path,
            backend,
            ["user-story", "update", "story-login", "--tag", "smoke", "--clear-tags"],
        )

        assert result.exit_code == 1
        assert backend.requests == []

    def test_list_filters_by_tag_ids_and_shows_tags(self, tmp_path, monkeypatch):
        monkeypatch.setenv("COLUMNS", "200")
        backend = FakeBackend()

        result = _invoke(
            tmp_path, backend, ["user-story", "list", "--tag", "checkout", "--tag", "SMOKE"]
        )

        assert result.exit_code == 0, result.output
        listed = backend.sent("GET", STORIES)[0]
        assert listed.url.params.get_list("tagId") == ["tag-checkout", "tag-smoke"]
        assert "Tags" in result.stdout
        assert "Checkout, smoke" in result.stdout


class TestRunStartByTag:
    def test_one_batch_covers_every_scenario_with_any_tag(self, tmp_path):
        backend = FakeBackend()

        result = _invoke(
            tmp_path, backend, ["run", "start", "--tag", "Checkout", "--web"], json_mode=True
        )

        assert result.exit_code == 0, result.output
        posted = json.loads(backend.sent("POST", BATCHES)[0].content)
        assert posted["userStoryIds"] == ["story-pay", "story-refund"]
        assert posted["targets"] == [{"platform": "web"}]
        assert json.loads(result.stdout)["batchId"] == "batch-1"

    def test_tag_without_scenarios_never_starts_a_batch(self, tmp_path):
        backend = FakeBackend()
        backend.tags = [*backend.tags, _tag("tag-empty", "empty")]

        result = _invoke(tmp_path, backend, ["run", "start", "--tag", "empty", "--web"])

        assert result.exit_code == 4
        assert backend.sent("POST", BATCHES) == []

    def test_scenario_and_tag_are_mutually_exclusive(self, tmp_path):
        backend = FakeBackend()

        both = _invoke(tmp_path, backend, ["run", "start", "Log in", "--tag", "smoke", "--web"])
        neither = _invoke(tmp_path, backend, ["run", "start", "--web"])

        assert both.exit_code == neither.exit_code == 1
        assert backend.requests == []
