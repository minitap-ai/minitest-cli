"""'apps private-network' against an in-memory testing-service."""

import json

import pytest
from click import unstyle
from typer.testing import CliRunner

from minitest_cli.commands.apps import app as apps_app
from tests._commit_transport import cli_context, make_settings, routed
from tests._network_settings_server import LAPTOP, MAC_MINI, FakeNetworkSettings

runner = CliRunner()


@pytest.fixture
def server() -> FakeNetworkSettings:
    return FakeNetworkSettings()


def _invoke(server: FakeNetworkSettings, tmp_path, *args: str, json_mode: bool = True):
    with routed(server.handle), cli_context(make_settings(tmp_path), json_mode=json_mode):
        return runner.invoke(apps_app, ["private-network", *args])


def _stderr(result) -> str:
    return " ".join(unstyle(result.stderr).split())


class TestShow:
    def test_show_human_names_the_connector(self, server, tmp_path):
        result = _invoke(server, tmp_path, "show", json_mode=False)
        assert result.exit_code == 0, result.output
        assert f"Connector: QA Mac mini (online) {MAC_MINI['id']}" in result.stdout
        assert "Domains: web.stg.pnqa.internal" in result.stdout

    def test_show_json_never_includes_the_token_prefix(self, server, tmp_path):
        result = _invoke(server, tmp_path, "show")
        assert result.exit_code == 0, result.output
        connector = json.loads(result.stdout)["connector"]
        assert connector["name"] == "QA Mac mini"
        assert "tokenPrefix" not in connector

    def test_show_warns_about_domains_the_connector_refuses(self, server, tmp_path):
        server.network["domains"] = ["api.corp.example"]
        result = _invoke(server, tmp_path, "show")
        assert result.exit_code == 0, result.output
        assert "allowlist refuses: api.corp.example" in _stderr(result)


class TestConnectors:
    def test_lists_workspace_connectors(self, server, tmp_path):
        result = _invoke(server, tmp_path, "connectors")
        assert result.exit_code == 0, result.output
        names = [c["name"] for c in json.loads(result.stdout)["connectors"]]
        assert names == ["QA Mac mini", "Laptop"]

    def test_empty_workspace_points_to_the_webapp(self, server, tmp_path):
        server.connectors = []
        result = _invoke(server, tmp_path, "connectors", json_mode=False)
        assert result.exit_code == 0, result.output
        assert "Workspace settings → Private network" in _stderr(result)


class TestSet:
    def test_connector_name_resolves_to_its_id_and_keeps_the_rest(self, server, tmp_path):
        result = _invoke(server, tmp_path, "set", "--connector", "laptop", "--port", "8443")
        assert result.exit_code == 0, result.output
        assert server.puts == [
            {
                "enabled": True,
                "connectorId": LAPTOP["id"],
                "ports": [8443],
                "domains": ["web.stg.pnqa.internal"],
            }
        ]
        assert "'Laptop' is offline" in _stderr(result)

    def test_disable_keeps_connector_and_domains(self, server, tmp_path):
        result = _invoke(server, tmp_path, "set", "--disable")
        assert result.exit_code == 0, result.output
        assert server.network == {
            "enabled": False,
            "connectorId": MAC_MINI["id"],
            "ports": [443],
            "domains": ["web.stg.pnqa.internal"],
        }

    def test_enable_without_connector_explains_where_to_create_one(self, server, tmp_path):
        server.network = {"enabled": False, "connectorId": None, "domains": [], "ports": [443]}
        server.connectors = []
        result = _invoke(server, tmp_path, "set", "--enable", "--domain", "api.corp.example")
        assert result.exit_code == 1
        assert "needs a connector" in _stderr(result)
        assert "Workspace settings → Private network" in _stderr(result)
        assert server.puts == []

    @pytest.mark.parametrize(
        ("args", "message"),
        [
            (["--connector", "Nope"], "No connector named 'Nope'"),
            (["--clear-domains"], "needs at least one --domain"),
            (["--domain", "corp.example/x"], "Invalid domain(s)"),
            (["--port", "0"], "Invalid value for '--port'"),
        ],
    )
    def test_invalid_input_is_refused_before_writing(self, server, tmp_path, args, message):
        result = _invoke(server, tmp_path, "set", *args)
        assert result.exit_code != 0
        assert message in _stderr(result)
        assert server.puts == []

    def test_forbidden_role_gets_a_clear_message(self, server, tmp_path):
        server.role_allows_writes = False
        result = _invoke(server, tmp_path, "set", "--disable")
        assert result.exit_code == 2
        assert "Only workspace owners and admins can change this setting" in _stderr(result)
        assert server.network["enabled"] is True
