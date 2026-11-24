"""`scenario create/update --persona` against an in-memory API."""

import pytest
from click import unstyle
from typer.testing import CliRunner

from minitest_cli.commands.user_story import app as scenario_app
from tests._commit_transport import cli_context, make_settings, routed
from tests._persona_server import STORY, FakePersonaApi

runner = CliRunner()


@pytest.fixture
def server() -> FakePersonaApi:
    return FakePersonaApi()


def _invoke(server: FakePersonaApi, tmp_path, *args: str, json_mode=False):
    with routed(server.handle), cli_context(make_settings(tmp_path), json_mode=json_mode):
        return runner.invoke(scenario_app, list(args), env={"COLUMNS": "250"})


def _stderr(result) -> str:
    return " ".join(unstyle(result.stderr).split())


class TestCreateWithPersonas:
    def test_personas_given_by_name_or_id_are_played(self, server, tmp_path):
        seller, buyer = server.persona("Seller"), server.persona("Denmark buyer")

        result = _invoke(
            server, tmp_path, "create", "--name", "Buy", "--persona", "seller", "--persona", buyer
        )

        assert result.exit_code == 0, result.output
        method, path, body = server.writes[-1]
        assert (method, path, body["personaIds"]) == ("POST", "/user-stories", [seller, buyer])
        assert "Personas: Seller, Denmark buyer" in _stderr(result)

    def test_an_unknown_persona_creates_nothing(self, server, tmp_path):
        result = _invoke(server, tmp_path, "create", "--name", "Buy", "--persona", "Nobody")

        assert result.exit_code == 4
        assert "No persona named 'Nobody'" in _stderr(result)
        assert server.writes == []


class TestUpdatePersonas:
    def test_persona_replaces_the_set_and_clear_empties_it(self, server, tmp_path):
        seller, buyer = server.persona("Seller"), server.persona("Buyer")
        server.bindings[(STORY, None)] = [seller]

        replaced = _invoke(server, tmp_path, "update", STORY, "--persona", "Buyer")
        after_replace = server.bindings[(STORY, None)]
        cleared = _invoke(server, tmp_path, "update", STORY, "--clear-personas")

        assert replaced.exit_code == 0, replaced.output
        assert after_replace == [buyer]
        assert "Personas: Buyer" in _stderr(replaced)
        assert cleared.exit_code == 0, cleared.output
        assert server.bindings[(STORY, None)] == []

    def test_other_edits_leave_the_personas_alone(self, server, tmp_path):
        seller = server.persona("Seller")
        server.bindings[(STORY, None)] = [seller]

        result = _invoke(server, tmp_path, "update", STORY, "--name", "Renamed")

        assert result.exit_code == 0, result.output
        assert "personaIds" not in server.writes[-1][2]
        assert server.bindings[(STORY, None)] == [seller]

    def test_persona_and_clear_together_are_refused(self, server, tmp_path):
        result = _invoke(server, tmp_path, "update", STORY, "--persona", "x", "--clear-personas")

        assert result.exit_code == 1
        assert "Use either --persona or --clear-personas, not both" in _stderr(result)
        assert server.writes == []
