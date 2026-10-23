"""`minitest secret create` (generated or empty secrets) and its `request` alias."""

import json

import httpx
import pytest

from minitest_cli.commands.secret import app
from tests._secret_router import SECRETS, Router, invoke, secret_row

_REQUESTS = f"{SECRETS}/requests"


def _created(**overrides) -> httpx.Response:
    return httpx.Response(201, json=secret_row(usages=[], **overrides))


def _empty_created() -> httpx.Response:
    return _created(
        name="STRIPE_KEY", kind="token", hasValue=False, version=0, pendingReason="Checkout"
    )


@pytest.fixture(autouse=True)
def _no_agent_env(monkeypatch):
    monkeypatch.delenv("MINITAP_SECRETS_SOCKET", raising=False)
    monkeypatch.delenv("STORY_RUN_ID", raising=False)


class TestCreateGenerate:
    def test_generate_posts_mode_and_options_in_agent_context(self, tmp_path):
        router = Router({("POST", SECRETS): _created(valueOrigin="generated")})
        args = ["create", "QA_PASSWORD", "--kind", "password", "--generate"]
        args += ["--length", "32", "--charset", "alnum", "--note", "Sign-up"]
        result = invoke(app, args, router, tmp_path, env={"STORY_RUN_ID": "r1"})
        assert result.exit_code == 0, result.output
        assert router.body("POST", SECRETS) == {
            "name": "QA_PASSWORD",
            "kind": "password",
            "mode": "generate",
            "length": 32,
            "charset": "alnum",
            "note": "Sign-up",
        }
        assert "{{secret:QA_PASSWORD}}" in result.output

    def test_generate_json_prints_server_metadata(self, tmp_path):
        router = Router({("POST", SECRETS): _created(valueOrigin="generated")})
        args = ["create", "QA_PASSWORD", "--kind", "password", "--generate", "--json"]
        result = invoke(app, args, router, tmp_path)
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["valueOrigin"] == "generated"

    @pytest.mark.parametrize("kind", ["card", "totp"])
    def test_generate_refuses_card_and_totp(self, tmp_path, kind):
        router = Router({})
        result = invoke(app, ["create", "X", "--kind", kind, "--generate"], router, tmp_path)
        assert result.exit_code == 1
        assert "password, token or text" in result.output
        assert not router.requests

    @pytest.mark.parametrize("length", ["11", "65"])
    def test_generate_rejects_length_out_of_range(self, tmp_path, length):
        router = Router({})
        args = ["create", "X", "--kind", "token", "--generate", "--length", length]
        assert invoke(app, args, router, tmp_path).exit_code == 1
        assert not router.requests

    def test_generate_rejects_reason(self, tmp_path):
        router = Router({})
        args = ["create", "X", "--kind", "token", "--generate", "--reason", "why"]
        result = invoke(app, args, router, tmp_path)
        assert result.exit_code == 1
        assert "--reason goes with --empty" in result.output

    def test_generate_on_old_server_explains(self, tmp_path):
        router = Router({("POST", SECRETS): httpx.Response(405, json={"detail": "Not Allowed"})})
        args = ["create", "X", "--kind", "token", "--generate"]
        result = invoke(app, args, router, tmp_path)
        assert result.exit_code == 4
        assert "does not support `secret create --generate`" in result.output

    def test_name_taken_shows_server_detail(self, tmp_path):
        taken = httpx.Response(409, json={"detail": "A secret named X already exists"})
        router = Router({("POST", SECRETS): taken})
        result = invoke(app, ["create", "X", "--kind", "token", "--generate"], router, tmp_path)
        assert result.exit_code == 1
        assert "already exists" in result.output


class TestCreateEmpty:
    def test_empty_posts_reason_and_scenario(self, tmp_path):
        router = Router({("POST", SECRETS): _empty_created()})
        args = ["create", "STRIPE_KEY", "--kind", "token", "--empty"]
        args += ["--reason", "Checkout", "--scenario", "s1"]
        result = invoke(app, args, router, tmp_path, env={"MINITAP_SECRETS_SOCKET": "/s"})
        assert result.exit_code == 0, result.output
        assert router.body("POST", SECRETS) == {
            "name": "STRIPE_KEY",
            "kind": "token",
            "mode": "empty",
            "reason": "Checkout",
            "userStoryId": "s1",
        }
        assert "minitest secret set STRIPE_KEY --kind token" in " ".join(result.output.split())

    def test_empty_card_is_allowed(self, tmp_path):
        router = Router({("POST", SECRETS): _empty_created()})
        args = ["create", "CARD", "--kind", "card", "--empty", "--reason", "Pay"]
        assert invoke(app, args, router, tmp_path).exit_code == 0
        assert router.body("POST", SECRETS)["kind"] == "card"

    def test_empty_needs_reason(self, tmp_path):
        router = Router({})
        result = invoke(app, ["create", "X", "--kind", "token", "--empty"], router, tmp_path)
        assert result.exit_code == 1
        assert "--empty needs --reason" in result.output
        assert not router.requests

    def test_empty_rejects_generate_options(self, tmp_path):
        router = Router({})
        args = ["create", "X", "--kind", "token", "--empty", "--reason", "r", "--length", "20"]
        assert invoke(app, args, router, tmp_path).exit_code == 1
        assert not router.requests

    @pytest.mark.parametrize("flags", [[], ["--generate", "--empty"]])
    def test_needs_exactly_one_mode(self, tmp_path, flags):
        router = Router({})
        result = invoke(app, ["create", "X", "--kind", "token", *flags], router, tmp_path)
        assert result.exit_code == 1
        assert "exactly one of --generate or --empty" in result.output

    def test_rejects_bad_name(self, tmp_path):
        router = Router({})
        args = ["create", "lower", "--kind", "token", "--generate"]
        assert invoke(app, args, router, tmp_path).exit_code == 1
        assert not router.requests

    @pytest.mark.parametrize("status", [404, 405])
    def test_empty_falls_back_to_requests_on_old_server(self, tmp_path, status):
        old = httpx.Response(status, json={"detail": "Not Found"})
        legacy = httpx.Response(201, json={"name": "STRIPE_KEY", "kind": "token"})
        router = Router({("POST", SECRETS): old, ("POST", _REQUESTS): legacy})
        args = ["create", "STRIPE_KEY", "--kind", "token", "--empty"]
        args += ["--reason", "Checkout", "--scenario", "s1"]
        result = invoke(app, args, router, tmp_path)
        assert result.exit_code == 0, result.output
        assert router.body("POST", _REQUESTS) == {
            "name": "STRIPE_KEY",
            "kind": "token",
            "reason": "Checkout",
            "storyId": "s1",
        }

    def test_empty_when_secrets_disabled(self, tmp_path):
        router = Router({})
        args = ["create", "X", "--kind", "token", "--empty", "--reason", "r"]
        result = invoke(app, args, router, tmp_path)
        assert result.exit_code == 4
        assert "not enabled" in result.output


class TestRequestAlias:
    def test_request_creates_empty_secret_and_warns(self, tmp_path):
        router = Router({("POST", SECRETS): _empty_created()})
        args = ["request", "STRIPE_KEY", "--kind", "token", "--reason", "Checkout"]
        result = invoke(app, args, router, tmp_path, env={"STORY_RUN_ID": "r1"})
        assert result.exit_code == 0, result.output
        assert "deprecated" in result.output
        body = router.body("POST", SECRETS)
        assert body == {
            "name": "STRIPE_KEY",
            "kind": "token",
            "mode": "empty",
            "reason": "Checkout",
        }

    def test_request_is_hidden_from_help(self, tmp_path):
        result = invoke(app, ["--help"], Router({}), tmp_path)
        assert "create" in result.output
        assert " request " not in result.output
