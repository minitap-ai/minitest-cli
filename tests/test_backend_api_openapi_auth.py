"""'apps backend-api set --openapi-auth' against an in-memory testing-service."""

import json

import pytest
from click import unstyle
from typer.testing import CliRunner

from minitest_cli.commands.apps import app as cli
from tests._backend_api_server import FakeBackendApi
from tests._commit_transport import cli_context, make_settings, routed

runner = CliRunner()
HEADER = ["--openapi-auth", "header", "--openapi-auth-header", "X-Desk-Key"]
SECRET = ["--openapi-auth-secret", "BACKEND_DESK_API_KEY"]


@pytest.fixture
def server() -> FakeBackendApi:
    return FakeBackendApi()


def _set(server: FakeBackendApi, tmp_path, *args: str, json_mode: bool = True):
    with routed(server.handle), cli_context(make_settings(tmp_path), json_mode=json_mode):
        return runner.invoke(cli, ["backend-api", "set", *args])


def _stderr(result) -> str:
    return " ".join(unstyle(result.stderr).split())


class TestSetOpenApiAuth:
    def test_bearer_is_saved_and_shown(self, server, tmp_path):
        result = _set(server, tmp_path, "--openapi-auth", "bearer", *SECRET, json_mode=False)

        assert result.exit_code == 0, result.output
        assert server.openapi_auth == {"type": "bearer", "secretName": "BACKEND_DESK_API_KEY"}
        assert "OpenAPI download: bearer secret=BACKEND_DESK_API_KEY" in result.stdout

    def test_changing_only_the_secret_keeps_the_header_name(self, server, tmp_path):
        _set(server, tmp_path, *HEADER, *SECRET)

        result = _set(server, tmp_path, "--openapi-auth-secret", "ADMIN_TOKEN")

        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["openapiAuth"] == {
            "type": "header",
            "headerName": "X-Desk-Key",
            "secretName": "ADMIN_TOKEN",
        }

    def test_none_clears_it(self, server, tmp_path):
        _set(server, tmp_path, "--openapi-auth", "query", "--openapi-auth-param", "k", *SECRET)

        result = _set(server, tmp_path, "--openapi-auth", "none")

        assert result.exit_code == 0, result.output
        assert server.openapi_auth == {"type": "none"}

    def test_other_options_leave_it_out_of_the_request(self, server, tmp_path):
        result = _set(server, tmp_path, "--disable")

        assert result.exit_code == 0, result.output
        assert "openapiAuth" not in server.puts[-1]

    def test_server_rejection_is_shown(self, server, tmp_path):
        args = ["--openapi-auth", "bearer", "--openapi-auth-secret", "NOT_THERE"]

        result = _set(server, tmp_path, *args)

        assert result.exit_code == 1
        assert "OpenAPI download secret not in this app's vault: NOT_THERE" in _stderr(result)
        assert server.openapi_auth == {"type": "none"}

    @pytest.mark.parametrize(
        ("args", "message"),
        [
            (["--openapi-auth", "header", *SECRET], "needs --openapi-auth-header"),
            (["--openapi-auth", "bearer"], "needs --openapi-auth-secret"),
            (["--openapi-auth", "none", *SECRET], "--openapi-auth-secret does not apply"),
            ([*SECRET, "--openapi-auth", "bearer", "--openapi-auth-param", "k"], "does not apply"),
            (["--openapi-auth", "cookie", *SECRET], "must be one of"),
        ],
    )
    def test_incomplete_or_stray_options_never_write(self, server, tmp_path, args, message):
        result = _set(server, tmp_path, *args)

        assert result.exit_code != 0
        assert message in _stderr(result)
        assert server.puts == []


class TestShowOpenApiAuth:
    def test_show_warns_when_the_download_secret_is_gone(self, server, tmp_path):
        _set(server, tmp_path, "--openapi-auth", "bearer", *SECRET)
        server.vault.discard("BACKEND_DESK_API_KEY")

        with routed(server.handle), cli_context(make_settings(tmp_path), json_mode=True):
            result = runner.invoke(cli, ["backend-api", "show"])

        assert json.loads(result.stdout)["openapiAuthSecretMissing"] is True
        assert "OpenAPI download secret BACKEND_DESK_API_KEY is not in the app vault" in _stderr(
            result
        )
