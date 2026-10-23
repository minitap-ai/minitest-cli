"""Brief, app-guide, glossary and knowledge history against an in-memory testing-service."""

import json
from typing import Any

import httpx
from typer.testing import CliRunner

from minitest_cli.commands import glossary, knowledge, knowledge_documents
from tests._commit_transport import cli_context, make_settings, routed

runner = CliRunner()

APP = "a0d9820f-5136-4f70-b46b-e5966f56bfb5"
BASE = f"/api/v1/apps/{APP}"
GROUPS = {
    "brief": knowledge_documents.brief_app,
    "app-guide": knowledge_documents.app_guide_app,
    "glossary": glossary.app,
    "knowledge": knowledge.app,
}


class FakeKnowledgeService:
    def __init__(self, *, enabled: bool = True) -> None:
        self.enabled = enabled
        self.documents: dict[str, list[dict[str, Any]]] = {"product-brief": [], "app-guide": []}
        self.terms: list[dict[str, Any]] = [
            {"id": "term-pod", "term": "Pod", "meaning": "A group of five", "aliases": []}
        ]
        self.requests: list[httpx.Request] = []
        self.reverted: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path, method = request.url.path.removeprefix(BASE + "/"), request.method
        if method != "GET" and not self.enabled:
            return httpx.Response(
                409, json={"error": "knowledge_v2_disabled", "message": "Not enabled."}
            )
        if path in self.documents:
            return self._document(path, request)
        if path == "glossary" and method == "GET":
            return httpx.Response(200, json={"terms": self.terms})
        if path == "glossary" and method == "POST":
            term = {"id": "term-new", **json.loads(request.content)}
            if any(t["term"].lower() == term["term"].lower() for t in self.terms):
                detail = f"This app's glossary already defines '{term['term']}'."
                return httpx.Response(409, json={"detail": detail})
            self.terms.append(term)
            return httpx.Response(201, json=term)
        if path.startswith("glossary/") and method == "PATCH":
            term = next(t for t in self.terms if t["id"] == path.split("/")[1])
            term.update(json.loads(request.content))
            return httpx.Response(200, json=term)
        if path.startswith("glossary/") and method == "DELETE":
            self.terms = [t for t in self.terms if t["id"] != path.split("/")[1]]
            return httpx.Response(204)
        if path.startswith("knowledge/history/") and path.endswith("/revert"):
            version_id = path.split("/")[2]
            if version_id not in {"v-9", "v-10"}:
                return httpx.Response(404, json={"detail": "Knowledge version not found"})
            self.reverted.append(version_id)
            return httpx.Response(204)
        if path == "knowledge/history":
            return self._history(request.url.params.get("element"))
        return httpx.Response(500, json={"detail": f"unexpected {method} {path}"})

    def _document(self, route: str, request: httpx.Request) -> httpx.Response:
        versions = self.documents[route]
        if request.method == "PUT":
            content = json.loads(request.content)["content"]
            if route == "product-brief" and len(content) > 2000:
                return httpx.Response(
                    422,
                    json={
                        "detail": [{"loc": ["body", "content"], "msg": "at most 2000 characters"}]
                    },
                )
            versions.append(
                {
                    "content": content,
                    "versionNumber": len(versions) + 1,
                    "actor": {
                        "kind": "user",
                        "id": "u1",
                        "channel": request.headers["X-Minitest-Channel"],
                    },
                    "createdAt": "2026-10-23T09:00:00Z",
                }
            )
        latest = versions[-1] if versions else {"content": "", "versionNumber": 0, "actor": None}
        return httpx.Response(200, json=latest)

    def _history(self, element: str | None) -> httpx.Response:
        if element is None:
            return httpx.Response(422, json={"detail": [{"loc": ["query", "element"]}]})
        entries = [_glossary_change(), _brief_change()]
        return httpx.Response(200, json=[e for e in entries if e["element"] == element])


def _glossary_change() -> dict[str, Any]:
    return {
        "versionId": "v-9",
        "element": "glossary",
        "versionNumber": None,
        "termId": "term-pod",
        "change": "updated",
        "actor": {"kind": "agent", "id": "maint", "channel": "knowledge_maintenance"},
        "createdAt": "2026-10-23T08:00:00Z",
        "before": {"term": "Pod"},
        "after": {"term": "Pod"},
    }


def _brief_change() -> dict[str, Any]:
    return {
        "versionId": "v-10",
        "element": "product_brief",
        "versionNumber": 3,
        "termId": None,
        "change": "updated",
        "actor": {"kind": "user", "id": "u1", "channel": "cli"},
        "createdAt": "2026-10-23T10:00:00Z",
        "before": "old",
        "after": "new",
    }


def _invoke(tmp_path, service: FakeKnowledgeService, args: list[str], *, json_mode=False):
    group, *rest = args
    with cli_context(make_settings(tmp_path), json_mode=json_mode), routed(service):
        return runner.invoke(GROUPS[group], rest, env={"COLUMNS": "200"})


class TestDocuments:
    def test_update_from_file_creates_a_cli_authored_version_that_get_prints(self, tmp_path):
        service = FakeKnowledgeService()
        brief = tmp_path / "brief.md"
        brief.write_text("Duolingo-style app for learning Turkish.", encoding="utf-8")

        updated = _invoke(tmp_path, service, ["brief", "update", "--content-file", str(brief)])
        shown = _invoke(tmp_path, service, ["brief", "get"], json_mode=True)

        assert updated.exit_code == 0, updated.output
        assert updated.stdout.strip() == "1"
        record = json.loads(shown.stdout)
        assert record["content"] == "Duolingo-style app for learning Turkish."
        assert record["actor"]["channel"] == "cli"

    def test_app_guide_get_without_content_says_nothing_is_written(self, tmp_path):
        result = _invoke(tmp_path, FakeKnowledgeService(), ["app-guide", "get"])

        assert result.exit_code == 0, result.output
        assert "No App guide written yet." in result.stderr
        assert result.stdout == ""

    def test_update_needs_exactly_one_content_source(self, tmp_path):
        service = FakeKnowledgeService()
        file = tmp_path / "guide.md"
        file.write_text("x", encoding="utf-8")

        neither = _invoke(tmp_path, service, ["app-guide", "update"])
        both = _invoke(
            tmp_path,
            service,
            ["app-guide", "update", "--content", "x", "--content-file", str(file)],
        )

        assert (neither.exit_code, both.exit_code) == (1, 1)
        assert service.requests == []

    def test_write_on_a_workspace_without_knowledge_v2_points_to_app_knowledge(self, tmp_path):
        result = _invoke(
            tmp_path, FakeKnowledgeService(enabled=False), ["brief", "update", "--content", "x"]
        )

        assert result.exit_code == 1
        assert "not enabled for this workspace" in result.stderr
        assert "minitest app-knowledge" in result.stderr

    def test_brief_over_the_server_limit_shows_the_field_error(self, tmp_path):
        result = _invoke(
            tmp_path, FakeKnowledgeService(), ["brief", "update", "--content", "x" * 2001]
        )

        assert result.exit_code == 1
        assert "content" in result.stderr
        assert "2000" in result.stderr


class TestGlossary:
    def test_add_then_list_shows_the_term_with_its_aliases(self, tmp_path):
        service = FakeKnowledgeService()

        added = _invoke(
            tmp_path,
            service,
            ["glossary", "add", "--term", "Streak", "--meaning", "Days in a row", "--alias", "run"],
        )
        listed = _invoke(tmp_path, service, ["glossary", "list"], json_mode=True)

        assert added.exit_code == 0, added.output
        streak = next(t for t in json.loads(listed.stdout)["terms"] if t["term"] == "Streak")
        assert streak == {
            "id": "term-new",
            "term": "Streak",
            "meaning": "Days in a row",
            "aliases": ["run"],
        }

    def test_add_existing_term_shows_the_conflict_and_keeps_the_original(self, tmp_path):
        service = FakeKnowledgeService()

        result = _invoke(
            tmp_path, service, ["glossary", "add", "--term", "pod", "--meaning", "Other"]
        )

        assert result.exit_code == 1
        assert "already defines 'pod'" in result.stderr
        assert [t["meaning"] for t in service.terms] == ["A group of five"]

    def test_update_by_term_name_sends_only_the_changed_fields(self, tmp_path):
        service = FakeKnowledgeService()

        result = _invoke(
            tmp_path, service, ["glossary", "update", "pod", "--meaning", "Up to five"]
        )

        assert result.exit_code == 0, result.output
        patch = [r for r in service.requests if r.method == "PATCH"]
        assert patch[0].url.path == f"{BASE}/glossary/term-pod"
        assert json.loads(patch[0].content) == {"meaning": "Up to five"}

    def test_update_unknown_term_exits_not_found(self, tmp_path):
        result = _invoke(
            tmp_path, FakeKnowledgeService(), ["glossary", "update", "boost", "--meaning", "x"]
        )

        assert result.exit_code == 4
        assert "Glossary term not found: boost" in result.stderr

    def test_remove_requires_yes_then_deletes(self, tmp_path):
        service = FakeKnowledgeService()

        refused = _invoke(tmp_path, service, ["glossary", "remove", "Pod"])
        removed = _invoke(tmp_path, service, ["glossary", "remove", "Pod", "--yes"])

        assert refused.exit_code == 1
        assert removed.exit_code == 0, removed.output
        assert service.terms == []


class TestHistory:
    def test_history_filters_by_element_and_names_the_author(self, tmp_path):
        service = FakeKnowledgeService()

        result = _invoke(tmp_path, service, ["knowledge", "history", "--element", "glossary"])

        assert result.exit_code == 0, result.output
        assert service.requests[0].url.params["element"] == "glossary"
        assert "Pod" in result.stdout
        assert "knowledge_maintenance" in result.stdout
        assert "v-9" in result.stdout

    def test_history_without_element_merges_every_element_newest_first(self, tmp_path):
        service = FakeKnowledgeService()

        result = _invoke(tmp_path, service, ["knowledge", "history"], json_mode=True)

        assert result.exit_code == 0, result.output
        changes = json.loads(result.stdout)
        assert [c["versionId"] for c in changes] == ["v-10", "v-9"]
        assert {r.url.params["element"] for r in service.requests} == {
            "product_brief",
            "app_guide",
            "glossary",
        }

    def test_revert_restores_a_version_listed_by_history(self, tmp_path):
        service = FakeKnowledgeService()

        reverted = _invoke(tmp_path, service, ["knowledge", "revert", "v-10"])
        unknown = _invoke(tmp_path, service, ["knowledge", "revert", "v-404"])

        assert reverted.exit_code == 0, reverted.output
        assert "v-10" in reverted.stderr
        assert unknown.exit_code == 4
        assert service.reverted == ["v-10"]
