"""One-run backend API URL flags on the commands that start runs."""

import pytest
from click import unstyle
from typer.testing import CliRunner

from minitest_cli.commands.run import app as cli
from tests._backend_api_server import DESK
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


class TestRunOverride:
    def test_run_all_sends_both_urls_for_that_run_only(self, server, tmp_path):
        before = dict(server.saved)
        args = ["--backend-base-url", f"{DESK}/", "--backend-openapi-url", f"{DESK}/spec.json"]
        result = _invoke(server, tmp_path, "all", "--web", *args)
        assert result.exit_code == 0, result.output
        assert server.batches[0]["backendApiOverride"] == {
            "baseUrl": f"{DESK}/",
            "openapiUrl": f"{DESK}/spec.json",
        }
        assert server.saved == before

    def test_from_commit_sends_only_the_given_flag(self, server, tmp_path):
        sha = "2c589b1b370be5397f6d8774940c989e9110a625"
        args = ["from-commit", sha, "--platform", "web", "--no-watch"]
        result = _invoke(server, tmp_path, *args, "--backend-openapi-url", f"{DESK}/v2.json")
        assert result.exit_code == 0, result.output
        assert server.batches[0]["backendApiOverride"] == {"openapiUrl": f"{DESK}/v2.json"}

    def test_run_without_flags_sends_no_override(self, server, tmp_path):
        result = _invoke(server, tmp_path, "all", "--web")
        assert result.exit_code == 0, result.output
        assert "backendApiOverride" not in server.batches[0]

    def test_rejected_override_surfaces_the_server_message(self, server, tmp_path):
        args = ["--backend-base-url", "http://169.254.169.254"]
        result = _invoke(server, tmp_path, "all", "--web", *args)
        assert result.exit_code == 3
        assert "cannot be used as a backend URL" in _stderr(result)
