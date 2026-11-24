"""`persona`, `test-account` and `scenario-binding *-personas` against an in-memory API."""

import json

import pytest
from click import unstyle
from typer.testing import CliRunner

from minitest_cli.commands import persona, test_account, user_story_bindings
from tests._commit_transport import cli_context, make_settings, routed
from tests._persona_server import STORY, FakePersonaApi

runner = CliRunner()


@pytest.fixture
def server() -> FakePersonaApi:
    return FakePersonaApi()


_GROUPS = {
    "persona": persona.app,
    "test-account": test_account.app,
    "scenario-binding": user_story_bindings.app,
}


def _invoke(server: FakePersonaApi, tmp_path, group: str, *args: str, json_mode=True, stdin=None):
    with routed(server.handle), cli_context(make_settings(tmp_path), json_mode=json_mode):
        return runner.invoke(_GROUPS[group], list(args), input=stdin, env={"COLUMNS": "250"})


def _stderr(result) -> str:
    return " ".join(unstyle(result.stderr).split())


class TestPersonaPool:
    def test_a_persona_with_two_accounts_shows_two_free_accounts(self, server, tmp_path):
        created = _invoke(
            server, tmp_path, "persona", "create", "--name", "Denmark buyer", "--exclusive"
        )
        _invoke(
            server,
            tmp_path,
            "test-account",
            "add",
            "--persona",
            "denmark buyer",
            "--username",
            "t7@test.com",
            "--password-stdin",
            stdin="hunter2\n",
        )
        _invoke(
            server,
            tmp_path,
            "test-account",
            "add",
            "--persona",
            "Denmark buyer",
            "--username",
            "t15@qa.minitap.ai",
        )

        pool = _invoke(server, tmp_path, "persona", "pool", "Denmark buyer", json_mode=False)

        assert created.exit_code == 0, created.output
        assert json.loads(created.stdout)["exclusiveUse"] is True
        assert pool.exit_code == 0, pool.output
        out = " ".join(unstyle(pool.stdout).split())
        assert "Denmark buyer: 2 free, 0 in use, 0 cooling down" in out
        assert "Denmark buyer 2" in out
        assert "hunter2" not in pool.stdout
        assert sorted(s.get("password", "") for s in server.secrets.values()) == ["", "hunter2"]

    def test_held_and_cooling_accounts_say_who_holds_them_and_until_when(self, server, tmp_path):
        seller = server.persona("Seller")
        for login in ("a@qa.minitap.ai", "b@qa.minitap.ai", "c@qa.minitap.ai"):
            _invoke(
                server, tmp_path, "test-account", "add", "--persona", seller, "--username", login
            )
        held, elsewhere, cooled = server.accounts.values()
        run = {"kind": "run", "subdagRunId": "run-1", "batchId": "b-1", "platform": "android"}
        held.update(state="in_use", holders=[run])
        other = {"kind": "other_workspace", "subdagRunId": None, "batchId": None, "platform": None}
        elsewhere.update(state="in_use", holders=[other])
        cooled.update(state="cooling_down", cooldownUntil="14:20", cooldownReason="rate_limited")

        pool = _invoke(server, tmp_path, "persona", "pool", seller, json_mode=False)

        out = " ".join(unstyle(pool.stdout).split())
        assert "In use by run run-1 · android" in out
        assert "In use by another workspace" in out
        assert "Cooling down until 14:20 (rate_limited)" in out

    def test_an_unknown_persona_name_is_not_found(self, server, tmp_path):
        result = _invoke(
            server,
            tmp_path,
            "test-account",
            "add",
            "--persona",
            "Nobody",
            "--username",
            "x@qa.minitap.ai",
        )

        assert result.exit_code == 4
        assert "No persona named 'Nobody'" in _stderr(result)
        assert server.accounts == {}


class TestPersonaRules:
    def test_a_taken_name_is_refused(self, server, tmp_path):
        server.persona("Seller")

        result = _invoke(server, tmp_path, "persona", "create", "--name", "SELLER")

        assert result.exit_code == 3
        assert "already exists" in _stderr(result)
        assert [p["name"] for p in server.personas.values()] == ["Seller"]

    def test_exclusive_use_turns_on_and_off_and_is_refused_on_new_user(self, server, tmp_path):
        seller = server.persona("Seller")
        new_user = server.persona("New user", kind="new_user")

        on = _invoke(server, tmp_path, "persona", "exclusive", "Seller", "on")
        on_state = server.personas[seller]["exclusiveUse"]
        off = _invoke(server, tmp_path, "persona", "exclusive", seller, "off")
        refused = _invoke(server, tmp_path, "persona", "exclusive", new_user, "on")

        assert (on.exit_code, off.exit_code) == (0, 0)
        assert on_state is True
        assert server.personas[seller]["exclusiveUse"] is False
        assert refused.exit_code == 3
        assert "cannot be marked for exclusive use" in _stderr(refused)

    def test_delete_is_refused_while_bound_and_needs_force(self, server, tmp_path):
        seller = server.persona("Seller")
        server.bindings[(STORY, None)] = [seller]

        unforced = _invoke(server, tmp_path, "persona", "delete", "Seller")
        refused = _invoke(server, tmp_path, "persona", "delete", "Seller", "--force")

        assert unforced.exit_code == 1
        assert refused.exit_code == 3
        assert "still bound" in _stderr(refused)
        assert seller in server.personas


class TestScenarioBinding:
    def test_personas_are_set_by_name_on_a_draft_branch(self, server, tmp_path):
        seller = server.persona("Seller")
        buyer = server.persona("Buyer")
        draft = "9b1d6d2e-0000-4000-8000-000000000001"

        result = _invoke(
            server,
            tmp_path,
            "scenario-binding",
            "set-personas",
            STORY,
            "--persona",
            "seller",
            "--persona",
            buyer,
            "--draft-feature",
            draft,
        )
        listed = _invoke(
            server,
            tmp_path,
            "scenario-binding",
            "list-personas",
            STORY,
            "--draft-feature",
            draft,
            json_mode=False,
        )
        on_main = _invoke(server, tmp_path, "scenario-binding", "list-personas", STORY)

        assert result.exit_code == 0, result.output
        assert server.writes[-1] == (
            "PUT",
            f"/user-stories/{STORY}/personas",
            {"personaIds": [seller, buyer], "draftFeatureId": draft},
        )
        assert "Seller" in listed.stdout and "Buyer" in listed.stdout
        assert json.loads(on_main.stdout)["items"] == []

    def test_clear_unbinds_every_persona(self, server, tmp_path):
        server.bindings[(STORY, None)] = [server.persona("Seller")]

        result = _invoke(server, tmp_path, "scenario-binding", "set-personas", STORY, "--clear")

        assert result.exit_code == 0, result.output
        assert server.bindings[(STORY, None)] == []


class TestTestAccounts:
    def test_move_remove_and_clear_cooldown_change_the_pool(self, server, tmp_path):
        seller, buyer = server.persona("Seller"), server.persona("Buyer")
        first = json.loads(
            _invoke(
                server,
                tmp_path,
                "test-account",
                "add",
                "--persona",
                seller,
                "--username",
                "a@qa.minitap.ai",
            ).stdout
        )["id"]
        second = json.loads(
            _invoke(
                server,
                tmp_path,
                "test-account",
                "add",
                "--persona",
                seller,
                "--username",
                "b@qa.minitap.ai",
            ).stdout
        )["id"]
        server.accounts[second].update(
            state="cooling_down", cooldownUntil="2026-11-24T14:20Z", cooldownReason="rate_limited"
        )

        moved = _invoke(server, tmp_path, "test-account", "move", first, "--persona", "Buyer")
        cleared = _invoke(server, tmp_path, "test-account", "clear-cooldown", second)
        removed = _invoke(server, tmp_path, "test-account", "remove", first, "--force")

        assert json.loads(moved.stdout)["personaId"] == buyer
        assert json.loads(cleared.stdout)["cooldownUntil"] is None
        assert removed.exit_code == 0
        assert list(server.accounts) == [second]

    def test_update_writes_credentials_on_the_account(self, server, tmp_path):
        seller = server.persona("Seller")
        account = json.loads(
            _invoke(
                server,
                tmp_path,
                "test-account",
                "add",
                "--persona",
                seller,
                "--username",
                "a@qa.minitap.ai",
            ).stdout
        )["id"]

        result = _invoke(
            server,
            tmp_path,
            "test-account",
            "update",
            account,
            "--password-stdin",
            stdin="s3cret\n",
            json_mode=False,
        )

        assert result.exit_code == 0, result.output
        assert "Test account updated" in _stderr(result)
        assert server.secrets[account]["password"] == "s3cret"
