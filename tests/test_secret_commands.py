"""`minitest secret list|describe|set|unset|rename|request` against a mocked testing-service."""

import json

import httpx
import pytest

from minitest_cli.commands import secret_value
from minitest_cli.commands.secret import app
from tests._secret_router import FAKE, SECRETS, Router, invoke, secret_row, vault

_REQUEST = {
    "name": "STRIPE_KEY",
    "kind": "token",
    "reason": "Checkout calls Stripe",
    "storyId": "s1",
    "storyName": "Checkout",
    "requestedBy": "mini",
    "createdAt": "2026-10-20T10:00:00Z",
}
_DISABLED = httpx.Response(404, json={"detail": "Not Found"})


@pytest.fixture(autouse=True)
def _no_agent_env(monkeypatch):
    monkeypatch.delenv("MINITAP_SECRETS_SOCKET", raising=False)
    monkeypatch.delenv("STORY_RUN_ID", raising=False)


class TestList:
    def test_list_prints_secrets_and_requests(self, tmp_path):
        router = Router({("GET", SECRETS): vault([secret_row()], [_REQUEST])})
        result = invoke(app, ["list"], router, tmp_path)
        assert result.exit_code == 0, result.output
        assert "ADMIN_PASSWORD" in result.output
        assert "Admin login" in result.output
        assert "STRIPE_KEY" in result.output

    def test_list_missing_json_returns_requests_only(self, tmp_path):
        router = Router({("GET", SECRETS): vault([secret_row()], [_REQUEST])})
        result = invoke(app, ["list", "--missing", "--json"], router, tmp_path)
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout) == {"requests": [_REQUEST]}

    def test_list_flag_off_prints_friendly_message(self, tmp_path):
        result = invoke(app, ["list"], Router({("GET", SECRETS): _DISABLED}), tmp_path)
        assert result.exit_code == 4
        assert "Secrets are not enabled for this workspace yet" in result.output

    def test_list_auth_error_exits_2(self, tmp_path):
        router = Router({("GET", SECRETS): httpx.Response(403, json={"detail": "nope"})})
        assert invoke(app, ["list"], router, tmp_path).exit_code == 2


class TestDescribe:
    def test_describe_shows_reference_and_usages(self, tmp_path):
        router = Router({("GET", SECRETS): vault([secret_row()])})
        result = invoke(app, ["describe", "ADMIN_PASSWORD"], router, tmp_path)
        assert result.exit_code == 0, result.output
        assert "{{secret:ADMIN_PASSWORD}}" in result.output
        assert "persona Admin (password)" in result.output

    def test_describe_card_lists_field_references(self, tmp_path):
        router = Router({("GET", SECRETS): vault([secret_row(name="CARD", kind="card")])})
        result = invoke(app, ["describe", "CARD", "--json"], router, tmp_path)
        assert result.exit_code == 0, result.output
        assert "{{secret:CARD.cvc}}" in json.loads(result.stdout)["references"]

    def test_describe_requested_secret(self, tmp_path):
        router = Router({("GET", SECRETS): vault([], [_REQUEST])})
        result = invoke(app, ["describe", "STRIPE_KEY"], router, tmp_path)
        assert result.exit_code == 0, result.output
        assert "requested, not set yet" in result.output

    def test_describe_unknown_exits_4(self, tmp_path):
        router = Router({("GET", SECRETS): vault()})
        assert invoke(app, ["describe", "NOPE"], router, tmp_path).exit_code == 4


class TestSet:
    def _router(self, name="ADMIN_PASSWORD"):
        saved = httpx.Response(201, json=secret_row(name=name, version=1))
        return Router({("PUT", f"{SECRETS}/{name}"): saved})

    def test_set_reads_value_from_stdin_and_never_prints_it(self, tmp_path):
        router = self._router()
        args = ["set", "ADMIN_PASSWORD", "--kind", "password", "--note", "Admin"]
        result = invoke(app, args, router, tmp_path, stdin=FAKE + "\n")
        assert result.exit_code == 0, result.output
        body = router.body("PUT", f"{SECRETS}/ADMIN_PASSWORD")
        assert body == {"kind": "password", "value": FAKE, "note": "Admin"}
        assert FAKE not in result.output
        assert "{{secret:ADMIN_PASSWORD}}" in result.output

    def test_set_card_from_json_stdin(self, tmp_path):
        router = self._router("CARD")
        card = {"number": "4242424242424242", "expiry": "12/34", "cvc": "123", "postalCode": "75"}
        result = invoke(
            app, ["set", "CARD", "--kind", "card"], router, tmp_path, stdin=json.dumps(card)
        )
        assert result.exit_code == 0, result.output
        fields = router.body("PUT", f"{SECRETS}/CARD")["fields"]
        assert fields == {
            "number": "4242424242424242",
            "expiry": "12/34",
            "cvc": "123",
            "postal_code": "75",
        }

    @pytest.mark.parametrize(
        "stdin, message",
        [
            ("not json", "JSON object"),
            ('{"number": "4242"}', "Missing card field(s): expiry, cvc"),
            ('{"number":"1","expiry":"1","cvc":"1","pin":"1"}', "Unknown card field(s): pin"),
        ],
    )
    def test_set_card_rejects_bad_input(self, tmp_path, stdin, message):
        router = self._router("CARD")
        result = invoke(app, ["set", "CARD", "--kind", "card"], router, tmp_path, stdin=stdin)
        assert result.exit_code == 1
        assert message in result.output
        assert not router.requests

    def test_set_totp_rejects_non_base32(self, tmp_path):
        router = self._router("OTP")
        result = invoke(
            app, ["set", "OTP", "--kind", "totp"], router, tmp_path, stdin="not-a-seed!"
        )
        assert result.exit_code == 1
        assert "base32" in result.output

    def test_set_totp_accepts_otpauth_url(self, tmp_path):
        router = self._router("OTP")
        url = "otpauth://totp/x?secret=JBSWY3DPEHPK3PXP"
        result = invoke(app, ["set", "OTP", "--kind", "totp"], router, tmp_path, stdin=url)
        assert result.exit_code == 0, result.output

    def test_set_refuses_tty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(secret_value, "stdin_is_tty", lambda: True)
        router = self._router()
        result = invoke(app, ["set", "ADMIN_PASSWORD", "--kind", "password"], router, tmp_path)
        assert result.exit_code == 1
        assert "Pipe the value" in result.output
        assert not router.requests

    def test_set_interactive_uses_hidden_prompt(self, tmp_path, monkeypatch):
        monkeypatch.setattr(secret_value, "stdin_is_tty", lambda: True)
        monkeypatch.setattr(secret_value.getpass, "getpass", lambda _prompt: FAKE)
        router = self._router()
        args = ["set", "ADMIN_PASSWORD", "--kind", "password", "--interactive"]
        result = invoke(app, args, router, tmp_path)
        assert result.exit_code == 0, result.output
        assert router.body("PUT", f"{SECRETS}/ADMIN_PASSWORD")["value"] == FAKE

    def test_set_interactive_mismatch_saves_nothing(self, tmp_path, monkeypatch):
        answers = iter([FAKE, "other"])
        monkeypatch.setattr(secret_value, "stdin_is_tty", lambda: True)
        monkeypatch.setattr(secret_value.getpass, "getpass", lambda _prompt: next(answers))
        router = self._router()
        args = ["set", "ADMIN_PASSWORD", "--kind", "password", "--interactive"]
        assert invoke(app, args, router, tmp_path).exit_code == 1
        assert not router.requests

    @pytest.mark.parametrize("var", ["MINITAP_SECRETS_SOCKET", "STORY_RUN_ID"])
    def test_set_refused_in_agent_context(self, tmp_path, var):
        router = self._router()
        args = ["set", "ADMIN_PASSWORD", "--kind", "password"]
        result = invoke(app, args, router, tmp_path, stdin=FAKE, env={var: "x"})
        assert result.exit_code == 1
        assert "secret create" in result.output
        assert not router.requests

    @pytest.mark.parametrize("name", ["lower", "MINITAP_KEY", "1ABC", "A" * 65])
    def test_set_rejects_bad_names(self, tmp_path, name):
        router = self._router()
        result = invoke(app, ["set", name, "--kind", "text"], router, tmp_path, stdin=FAKE)
        assert result.exit_code == 1
        assert not router.requests

    def test_set_empty_value_rejected(self, tmp_path):
        router = self._router()
        result = invoke(
            app, ["set", "ADMIN_PASSWORD", "--kind", "text"], router, tmp_path, stdin="\n"
        )
        assert result.exit_code == 1
        assert not router.requests


class TestManage:
    def test_unset_deletes(self, tmp_path):
        router = Router({("DELETE", f"{SECRETS}/OLD"): httpx.Response(204)})
        result = invoke(app, ["unset", "OLD"], router, tmp_path)
        assert result.exit_code == 0, result.output
        assert router.called("DELETE") == [f"{SECRETS}/OLD"]

    def test_unset_in_use_lists_usages(self, tmp_path):
        usages = [{"type": "scenario", "id": "s1", "name": "Login"}]
        conflict = httpx.Response(409, json={"usages": usages})
        router = Router({("DELETE", f"{SECRETS}/OLD"): conflict})
        result = invoke(app, ["unset", "OLD"], router, tmp_path)
        assert result.exit_code == 6
        assert "scenario Login" in result.output

    def test_unset_unknown_secret_shows_detail(self, tmp_path):
        missing = httpx.Response(404, json={"detail": "Secret OLD not found"})
        router = Router({("DELETE", f"{SECRETS}/OLD"): missing})
        result = invoke(app, ["unset", "OLD"], router, tmp_path)
        assert result.exit_code == 4
        assert "Secret OLD not found" in result.output

    def test_rename_sends_new_name(self, tmp_path):
        router = Router(
            {("PATCH", f"{SECRETS}/OLD"): httpx.Response(200, json=secret_row(name="NEW"))}
        )
        result = invoke(app, ["rename", "OLD", "NEW"], router, tmp_path)
        assert result.exit_code == 0, result.output
        assert router.body("PATCH", f"{SECRETS}/OLD") == {"newName": "NEW"}
        assert "{{secret:NEW}}" in result.output
