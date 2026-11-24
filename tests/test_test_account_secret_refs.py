"""`test-account add/update`: secret pointers, card fields and clears, as sent to the API."""

import httpx
import pytest

from minitest_cli.commands.test_account import app
from tests._secret_router import APP, PROFILES, Router, invoke

PERSONA = "7d4a1c0e-0000-4000-8000-000000000001"
ADD = f"/api/v1/apps/{APP}/personas/{PERSONA}/accounts"
ACCOUNT = f"{PROFILES}/p1"
_ACCOUNT = {"id": "p1", "personaId": PERSONA, "name": "Admin", "username": "admin@x.io"}


class TestAddSecretRefs:
    def test_add_sends_secret_pointers(self, tmp_path):
        router = Router({("POST", ADD): httpx.Response(201, json=_ACCOUNT)})
        args = ["add", "--persona", PERSONA, "--password-secret", "ADMIN_PASSWORD"]
        args += ["--otp-secret", "ADMIN_OTP", "--card-secret", "STRIPE_CARD"]

        result = invoke(app, args, router, tmp_path)

        assert result.exit_code == 0, result.output
        assert router.body("POST", ADD) == {
            "passwordSecret": "ADMIN_PASSWORD",
            "otpSecret": "ADMIN_OTP",
            "cardSecret": "STRIPE_CARD",
        }

    @pytest.mark.parametrize(
        "flags",
        [
            ["--password", "x", "--password-secret", "ADMIN_PASSWORD"],
            ["--otp-secret", "bad"],
        ],
    )
    def test_add_refuses_raw_value_with_pointer_or_bad_name(self, tmp_path, flags):
        router = Router({("POST", ADD): httpx.Response(201, json=_ACCOUNT)})

        result = invoke(app, ["add", "--persona", PERSONA, *flags], router, tmp_path)

        assert result.exit_code == 1
        assert not router.requests


class TestUpdate:
    def test_update_sets_and_clears_pointers(self, tmp_path):
        router = Router({("PATCH", ACCOUNT): httpx.Response(200, json=_ACCOUNT)})
        args = ["update", "p1", "--password-secret", "NEW_PASSWORD", "--card-secret", ""]

        result = invoke(app, [*args, "--clear-password"], router, tmp_path)

        assert result.exit_code == 0, result.output
        assert router.body("PATCH", ACCOUNT) == {
            "password": None,
            "passwordSecret": "NEW_PASSWORD",
            "cardSecret": None,
        }

    def test_update_changes_one_card_field_and_keeps_the_rest(self, tmp_path):
        stored = {**_ACCOUNT, "testCard": {"number": "4242", "cvc": "123", "holderName": "Ada"}}
        router = Router(
            {
                ("GET", ACCOUNT): httpx.Response(200, json=stored),
                ("PATCH", ACCOUNT): httpx.Response(200, json=stored),
            }
        )

        result = invoke(app, ["update", "p1", "--test-card-cvc", "999"], router, tmp_path)

        assert result.exit_code == 0, result.output
        assert router.body("PATCH", ACCOUNT) == {
            "test_card": {"number": "4242", "cvc": "999", "holder_name": "Ada"}
        }

    def test_update_clears_fields_with_explicit_nulls(self, tmp_path):
        router = Router({("PATCH", ACCOUNT): httpx.Response(200, json=_ACCOUNT)})
        args = ["update", "p1", "--clear-username", "--clear-phone-number", "--clear-test-card"]

        result = invoke(app, [*args, "--clear-static-otp-code"], router, tmp_path)

        assert result.exit_code == 0, result.output
        assert router.body("PATCH", ACCOUNT) == {
            "username": None,
            "phone_number": None,
            "static_otp_code": None,
            "test_card": None,
        }
        assert router.called("GET") == []

    @pytest.mark.parametrize(
        "flags",
        [
            ["--password", "x", "--clear-password"],
            ["--test-card-cvc", "999", "--clear-test-card"],
            ["--test-card-cvc", "123", "--card-secret", "CARD"],
            ["--exclusive"],
        ],
    )
    def test_update_refuses_conflicting_or_removed_flags(self, tmp_path, flags):
        router = Router({})

        result = invoke(app, ["update", "p1", *flags], router, tmp_path)

        assert result.exit_code != 0
        assert not router.requests
