"""'apps residential-proxy' against an in-memory testing-service."""

import json

import pytest
from click import unstyle
from typer.testing import CliRunner

from minitest_cli.commands.apps import app as apps_app
from tests._commit_transport import cli_context, make_settings, routed
from tests._network_settings_server import FakeNetworkSettings

runner = CliRunner()


@pytest.fixture
def server() -> FakeNetworkSettings:
    return FakeNetworkSettings()


def _invoke(server: FakeNetworkSettings, tmp_path, *args: str, json_mode: bool = True):
    with routed(server.handle), cli_context(make_settings(tmp_path), json_mode=json_mode):
        return runner.invoke(apps_app, ["residential-proxy", *args])


class TestShow:
    def test_show_json_returns_server_config(self, server, tmp_path):
        result = _invoke(server, tmp_path, "show")
        assert result.exit_code == 0, result.output
        data = json.loads(result.stdout)
        assert data["enabled"] is True
        assert data["country"] == "tr"
        assert data["allowedDomains"] == ["ipinfo.io"]

    def test_show_human_lists_settings(self, server, tmp_path):
        result = _invoke(server, tmp_path, "show", json_mode=False)
        assert result.exit_code == 0, result.output
        assert "Country: tr" in result.stdout
        assert "Domains: ipinfo.io" in result.stdout


class TestSet:
    def test_set_changes_only_what_was_passed(self, server, tmp_path):
        result = _invoke(server, tmp_path, "set", "--country", "FR", "--domain", "*.Example.com")
        assert result.exit_code == 0, result.output
        assert server.puts == [
            {"enabled": True, "country": "fr", "allowedDomains": ["ipinfo.io", "*.example.com"]}
        ]
        assert json.loads(result.stdout)["country"] == "fr"

    def test_clear_domains_then_add_replaces_the_list(self, server, tmp_path):
        result = _invoke(server, tmp_path, "set", "--clear-domains", "--domain", "api.x.io")
        assert result.exit_code == 0, result.output
        assert server.proxy["allowedDomains"] == ["api.x.io"]

    def test_disable_and_remove_domain(self, server, tmp_path):
        result = _invoke(server, tmp_path, "set", "--disable", "--remove-domain", "ipinfo.io")
        assert result.exit_code == 0, result.output
        assert server.proxy == {"enabled": False, "country": "tr", "allowedDomains": []}

    @pytest.mark.parametrize(
        ("args", "message"),
        [
            (["--country", "xx"], "Pick one of: tr, fr, de, gb, us"),
            (["--domain", "https://ipinfo.io/path"], "Invalid domain(s)"),
            (["--domain", "a.io", "--domain", "b.io", "--domain", "c.io"], "Too many domains: 4"),
            (["--remove-domain", "nope.io"], "Not in the current domain list: nope.io"),
            ([], "Nothing to change"),
        ],
    )
    def test_invalid_input_is_refused_before_writing(self, server, tmp_path, args, message):
        result = _invoke(server, tmp_path, "set", *args)
        assert result.exit_code == 1
        assert message in unstyle(result.stderr).replace("\n", " ")
        assert server.puts == []

    def test_unavailable_workspace_is_explained(self, server, tmp_path):
        server.available = False
        result = _invoke(server, tmp_path, "set", "--enable")
        assert result.exit_code == 1
        assert "cannot use the residential proxy" in result.stderr
        assert server.puts == []

    def test_forbidden_role_gets_a_clear_message(self, server, tmp_path):
        server.role_allows_writes = False
        result = _invoke(server, tmp_path, "set", "--disable")
        assert result.exit_code == 2
        assert "Only workspace owners and admins can change this setting" in unstyle(result.stderr)
        assert server.proxy["enabled"] is True
