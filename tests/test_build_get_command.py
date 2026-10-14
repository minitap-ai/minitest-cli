"""Behavior tests for `minitest build get`."""

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
from tests._commit_transport import make_settings, routed
from typer.testing import CliRunner

from minitest_cli.commands.build_fix_prompts import WITHHELD_NOTICE
from minitest_cli.main import app

runner = CliRunner()
APP_ID = "a0d9820f-5136-4f70-b46b-e5966f56bfb5"
BUILD_ID = "6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a4b"
FOREIGN_BUILD_ID = "0b6d1f4e-2c3a-4e5f-9a8b-7c6d5e4f3a2b"
BUILD = {
    "id": BUILD_ID,
    "appId": APP_ID,
    "kind": "native",
    "platform": "ios",
    "status": "completed",
    "originalName": "Shop.app.zip",
    "sizeBytes": 2048,
    "commitSha": "a1b2c3d4e5f6",
    "commitTitle": "feat: checkout v2",
    "appVersion": "4.2.0",
    "buildNumber": "317",
    "verificationStatus": "verified",
    "createdAt": "2026-10-14T09:30:00Z",
}


def _serve(build: dict[str, Any]):
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path == f"/api/v1/apps/{APP_ID}/builds/{BUILD_ID}":
            return httpx.Response(200, json=build)
        return httpx.Response(404, json={"message": "Build not found"})

    return handler, seen


def _invoke(tmp_path: Path, build: dict[str, Any], args: list[str]):
    handler, seen = _serve(build)
    with (
        routed(handler),
        patch("minitest_cli.main.get_settings", return_value=make_settings(tmp_path)),
        patch("minitest_cli.main.check_for_updates"),
    ):
        return runner.invoke(app, args), seen


class TestBuildGet:
    def test_get_returns_the_app_build_as_json(self, tmp_path: Path) -> None:
        result, seen = _invoke(tmp_path, BUILD, ["--json", "build", "get", BUILD_ID])

        assert result.exit_code == 0
        assert seen == [f"/api/v1/apps/{APP_ID}/builds/{BUILD_ID}"]
        payload = json.loads(result.stdout)
        assert payload["id"] == BUILD_ID
        assert (payload["appVersion"], payload["buildNumber"]) == ("4.2.0", "317")
        assert payload["commitTitle"] == "feat: checkout v2"
        assert payload["verificationStatus"] == "verified"
        assert payload["guidance"] is None

    def test_get_withholds_infra_failure_details(self, tmp_path: Path) -> None:
        failed = {
            **BUILD,
            "status": "failed",
            "errorClass": "infra",
            "errorSummary": "builder disk full",
            "errorFixPrompt": "ssh into the builder",
        }

        result, _ = _invoke(tmp_path, failed, ["--json", "build", "get", BUILD_ID])

        payload = json.loads(result.stdout)
        assert payload["guidance"] == {"source": "withheld", "text": WITHHELD_NOTICE}
        assert payload["errorSummary"] == WITHHELD_NOTICE
        assert payload["errorFixPrompt"] is None

    def test_get_shows_the_version_in_human_mode(self, tmp_path: Path) -> None:
        result, _ = _invoke(tmp_path, BUILD, ["build", "get", BUILD_ID])

        assert result.exit_code == 0
        assert "Build 4.2.0 (317)" in result.stdout
        assert "completed" in result.stdout

    def test_get_a_build_of_another_app_is_not_found(self, tmp_path: Path) -> None:
        result, _ = _invoke(tmp_path, BUILD, ["--json", "build", "get", FOREIGN_BUILD_ID])

        assert result.exit_code == 4
        assert "Build not found" in result.stderr
        assert result.stdout == ""

    def test_get_rejects_a_non_uuid_without_calling_the_api(self, tmp_path: Path) -> None:
        result, seen = _invoke(tmp_path, BUILD, ["build", "get", "317"])

        assert result.exit_code == 1
        assert "not a valid UUID" in result.stderr
        assert seen == []
