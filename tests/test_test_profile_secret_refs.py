"""`test-profile create/update --password-secret/--otp-secret/--card-secret`."""

import httpx

from minitest_cli.commands.test_profile import app
from tests._secret_router import PROFILES, Router, invoke

_PROFILE = {"id": "p1", "name": "Admin", "username": "admin@x.io"}


class TestProfileSecretRefs:
    def test_create_sends_secret_pointers(self, tmp_path):
        router = Router({("POST", PROFILES): httpx.Response(201, json=_PROFILE)})
        args = [
            "create",
            "--name",
            "Admin",
            "--password-secret",
            "ADMIN_PASSWORD",
            "--otp-secret",
            "ADMIN_OTP",
            "--card-secret",
            "STRIPE_CARD",
        ]
        result = invoke(app, args, router, tmp_path)
        assert result.exit_code == 0, result.output
        assert router.body("POST", PROFILES) == {
            "name": "Admin",
            "passwordSecret": "ADMIN_PASSWORD",
            "otpSecret": "ADMIN_OTP",
            "cardSecret": "STRIPE_CARD",
        }

    def test_create_rejects_raw_password_with_secret(self, tmp_path):
        router = Router({("POST", PROFILES): httpx.Response(201, json=_PROFILE)})
        args = ["create", "--name", "A", "--password", "x", "--password-secret", "ADMIN_PASSWORD"]
        result = invoke(app, args, router, tmp_path)
        assert result.exit_code == 1
        assert "not both" in result.output
        assert not router.requests

    def test_create_rejects_invalid_secret_name(self, tmp_path):
        router = Router({("POST", PROFILES): httpx.Response(201, json=_PROFILE)})
        result = invoke(app, ["create", "--name", "A", "--otp-secret", "bad"], router, tmp_path)
        assert result.exit_code == 1
        assert not router.requests

    def test_update_sets_and_clears_pointers(self, tmp_path):
        path = f"{PROFILES}/p1"
        router = Router({("PATCH", path): httpx.Response(200, json=_PROFILE)})
        args = [
            "update",
            "p1",
            "--password-secret",
            "NEW_PASSWORD",
            "--card-secret",
            "",
            "--clear-password",
        ]
        result = invoke(app, args, router, tmp_path)
        assert result.exit_code == 0, result.output
        assert router.body("PATCH", path) == {
            "password": None,
            "passwordSecret": "NEW_PASSWORD",
            "cardSecret": None,
        }

    def test_update_rejects_card_fields_with_card_secret(self, tmp_path):
        router = Router({})
        args = ["update", "p1", "--test-card-cvc", "123", "--card-secret", "CARD"]
        assert invoke(app, args, router, tmp_path).exit_code == 1
        assert not router.requests
