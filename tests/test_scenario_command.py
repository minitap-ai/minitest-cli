"""Renamed command groups survive under their old name as a hidden, warning alias."""

import json
import re
from unittest.mock import patch

import httpx
import pytest
from click import unstyle
from typer.testing import CliRunner

from minitest_cli.core.config import Settings
from minitest_cli.main import app

runner = CliRunner()

STORY = {"id": "story-1", "name": "Login", "acceptanceCriteria": [], "testProfiles": []}
DRAFTS: list[dict[str, str]] = []
FILES = {"items": [{"id": "file-1", "name": "avatar.png", "kind": "image"}]}
BACKEND = {
    "/api/v1/apps/app-123/user-stories/story-1": STORY,
    "/api/v1/apps/app-123/user-stories/story-1/files": FILES,
    "/api/v1/apps/app-123/draft-features": DRAFTS,
}


def _invoke(args: list[str]):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=BACKEND[request.url.path])

    async_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    settings = Settings(token="test-token", app_id="app-123")
    with (
        patch("minitest_cli.main.get_settings", return_value=settings),
        patch("minitest_cli.main.check_for_updates"),
        patch(
            "minitest_cli.api.client.httpx.AsyncClient",
            side_effect=lambda **kwargs: async_client(**kwargs, transport=transport),
        ),
    ):
        return runner.invoke(app, args)


@pytest.mark.parametrize(
    ("new", "legacy", "args", "expected"),
    [
        ("scenario", "user-story", ["get", "story-1"], STORY),
        ("scenario-binding", "user-story-binding", ["list-files", "story-1"], FILES),
        ("draft", "df", ["list"], DRAFTS),
    ],
)
class TestLegacyAlias:
    def test_json_stdout_is_identical_and_unchanged(self, new, legacy, args, expected):
        current = _invoke(["--json", new, *args])
        deprecated = _invoke(["--json", legacy, *args])

        assert current.exit_code == deprecated.exit_code == 0, deprecated.output
        assert deprecated.stdout == current.stdout
        assert json.loads(deprecated.stdout) == expected

    def test_only_the_legacy_name_warns_once_on_stderr(self, new, legacy, args, expected):
        current = _invoke(["--json", new, *args])
        deprecated = _invoke(["--json", legacy, *args])

        warning = f"`minitest {legacy}` is deprecated; use `minitest {new}` instead."
        assert " ".join(unstyle(deprecated.stderr).split()).count(warning) == 1
        assert "deprecated" not in deprecated.stdout
        assert "deprecated" not in current.stderr


def test_root_help_lists_scenario_commands_and_hides_legacy_ones():
    result = runner.invoke(app, ["--help"], terminal_width=200)

    commands = set(re.findall(r"│ (\S+)", unstyle(result.stdout)))
    assert {"scenario", "scenario-binding", "draft"} <= commands
    assert not {"user-story", "user-story-binding", "df"} & commands
