"""'apps backend-api' against an in-memory testing-service."""

import json

import pytest
from click import unstyle
from typer.testing import CliRunner

from minitest_cli.commands.apps import app as cli
from tests._backend_api_server import DESK, NOTES, OTHER
from tests._backend_api_server import FakeBackendApi
from tests._commit_transport import cli_context, make_settings, routed

runner = CliRunner()


@pytest.fixture
def server() -> FakeBackendApi:
    return FakeBackendApi()


def _invoke(server: FakeBackendApi, tmp_path, *args: str, json_mode: bool = True):
    with routed(server.handle), cli_context(make_settings(tmp_path), json_mode=json_mode):
        return runner.invoke(cli, list(args))


def _stderr(result) -> str:
    return " ".join(unstyle(result.stderr).split())


class TestShow:
    def test_show_human_lists_urls_secrets_and_skill(self, server, tmp_path):
        result = _invoke(server, tmp_path, "backend-api", "show", json_mode=False)
        assert result.exit_code == 0, result.output
        assert f"Base URL: {DESK}" in result.stdout
        assert f"OpenAPI URL: {DESK}/openapi.json" in result.stdout
        assert "Authentication secrets: BACKEND_DESK_API_KEY" in result.stdout
        assert f"Skill: desk-notes {NOTES['id']}" in result.stdout

    def test_show_warns_about_secrets_gone_from_the_vault(self, server, tmp_path):
        server.vault.discard("BACKEND_DESK_API_KEY")
        result = _invoke(server, tmp_path, "backend-api", "show")
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["missingSecretNames"] == ["BACKEND_DESK_API_KEY"]
        assert "Not in the app vault anymore: BACKEND_DESK_API_KEY" in _stderr(result)


class TestSet:
    def test_disable_keeps_every_other_field(self, server, tmp_path):
        before = dict(server.saved)
        result = _invoke(server, tmp_path, "backend-api", "set", "--disable")
        assert result.exit_code == 0, result.output
        assert server.saved == {**before, "enabled": False}
        assert json.loads(result.stdout)["enabled"] is False

    def test_secrets_are_added_removed_and_cleared_in_order(self, server, tmp_path):
        args = ["--remove-secret", "BACKEND_DESK_API_KEY", "--secret", "ADMIN_TOKEN"]
        result = _invoke(server, tmp_path, "backend-api", "set", *args)
        assert result.exit_code == 0, result.output
        assert server.saved["authenticationSecretNames"] == ["ADMIN_TOKEN"]

        result = _invoke(server, tmp_path, "backend-api", "set", "--clear-secrets")
        assert result.exit_code == 0, result.output
        assert server.saved["authenticationSecretNames"] == []

    def test_skill_is_resolved_by_name_then_cleared(self, server, tmp_path):
        result = _invoke(server, tmp_path, "backend-api", "set", "--skill", "desk-admin")
        assert result.exit_code == 0, result.output
        assert server.saved["skillId"] == OTHER["id"]

        result = _invoke(server, tmp_path, "backend-api", "set", "--clear-skill")
        assert result.exit_code == 0, result.output
        assert server.saved["skillId"] is None

    def test_reserved_url_is_rejected_with_the_server_reason(self, server, tmp_path):
        before = dict(server.saved)
        args = ["--base-url", "http://169.254.169.254/latest"]
        result = _invoke(server, tmp_path, "backend-api", "set", *args)
        assert result.exit_code == 1
        assert "it points at a private or reserved address" in _stderr(result)
        assert server.saved == before

    @pytest.mark.parametrize(
        ("args", "message"),
        [
            ([], "Nothing to change"),
            (["--remove-secret", "NOPE"], "Not an authentication secret of this app: NOPE"),
            (["--skill", "desk-notes", "--clear-skill"], "not both"),
            (["--skill", "missing"], "Skill 'missing' not found"),
        ],
    )
    def test_invalid_input_never_writes(self, server, tmp_path, args, message):
        result = _invoke(server, tmp_path, "backend-api", "set", *args)
        assert result.exit_code != 0
        assert message in _stderr(result)
        assert server.puts == []
