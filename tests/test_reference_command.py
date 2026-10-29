"""`minitest reference` against an in-memory testing-service, and its bundled fallback."""

import json
from unittest.mock import patch

import httpx
import pytest
from click import unstyle
from typer.testing import CliRunner

from minitest_cli.main import app
from minitest_cli.utils import reference_docs, skill_bundle
from tests._commit_transport import routed

runner = CliRunner()

SERVED_INDEX = [
    {"topic": "suite-schemas", "title": "Suite Schema", "summary": "The suite.yaml schema."},
    {"topic": "brand-new-topic", "title": "New", "summary": "Only the server knows it."},
]
SERVED_DOC = "# Brand new\n\nServed by Minitest.\n"


@pytest.fixture(autouse=True)
def _no_update_check():
    with patch("minitest_cli.main.check_for_updates", return_value=None):
        yield


@pytest.fixture(autouse=True)
def _api_url(monkeypatch):
    monkeypatch.setenv("MINITEST_API_URL", "https://testing.example")


def _server(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/api/skills/reference":
        return httpx.Response(200, json=SERVED_INDEX)
    if path == "/api/skills/reference/brand-new-topic":
        return httpx.Response(200, text=SERVED_DOC, headers={"content-type": "text/markdown"})
    topics = [entry["topic"] for entry in SERVED_INDEX]
    return httpx.Response(
        404, json={"error": "not_found", "message": "x", "details": {"topics": topics}}
    )


def _old_backend(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(404, json={"error": "not_found", "message": "Not Found", "details": {}})


def _offline(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("Connection refused", request=request)


def _invoke(handler, *args: str):
    with routed(handler):
        return runner.invoke(app, list(args))


def _stderr(result) -> str:
    return " ".join(unstyle(result.stderr).split())


class TestServed:
    def test_list_shows_the_topics_the_server_knows(self):
        result = _invoke(_server, "reference")
        assert result.exit_code == 0, result.output
        assert "brand-new-topic" in result.stdout
        assert "Only the server knows it." in result.stdout

    def test_list_json_is_the_server_index(self):
        result = _invoke(_server, "--json", "reference")
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout) == SERVED_INDEX

    def test_topic_prints_the_served_markdown_on_stdout(self):
        result = _invoke(_server, "reference", "brand-new-topic")
        assert result.exit_code == 0, result.output
        assert result.stdout == SERVED_DOC

    def test_typo_exits_not_found_and_suggests_the_closest_topic(self):
        result = _invoke(_server, "reference", "suite-schema")
        assert result.exit_code == 4
        assert result.stdout == ""
        assert "Topics: suite-schemas, brand-new-topic" in _stderr(result)
        assert "Did you mean 'suite-schemas'?" in _stderr(result)


@pytest.mark.parametrize("handler", [_offline, _old_backend], ids=["offline", "old-backend"])
class TestBundledFallback:
    def test_list_reads_the_bundled_index(self, handler):
        result = _invoke(handler, "--json", "reference")
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout) == reference_docs.bundled_index()
        assert "using the copy bundled with minitest-cli" in _stderr(result)

    def test_every_bundled_topic_prints_its_bundled_file(self, handler):
        reference_dir = skill_bundle.bundle_dir() / "reference"
        for entry in reference_docs.bundled_index():
            result = _invoke(handler, "reference", entry["topic"])
            assert result.exit_code == 0, result.output
            assert result.stdout == (reference_dir / f"{entry['topic']}.md").read_text()

    def test_typo_suggests_from_the_bundled_index(self, handler):
        result = _invoke(handler, "reference", "test-suite-desing")
        assert result.exit_code == 4
        assert "Did you mean 'test-suite-design'?" in _stderr(result)
