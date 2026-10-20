"""Physical devices: ``build upload --physical`` and ``run … --ios-physical/--android-physical``."""

import json

import httpx
import pytest
import typer
from typer.testing import CliRunner

from minitest_cli.commands.build import app as build_app
from minitest_cli.commands.run import app as run_app
from minitest_cli.core.config import Settings

STORY_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
BUILD = {
    "id": "build-1",
    "appId": "app-123",
    "platform": "ios",
    "status": "completed",
    "storagePath": "builds/build-1.ipa",
    "originalName": "App.ipa",
    "sizeBytes": 8,
    "createdAt": "2026-10-20T10:00:00Z",
}
BATCH = {
    "id": "batch-1",
    "appId": "app-123",
    "tenantId": "tenant-1",
    "source": "api",
    "status": "pending",
    "createdAt": "2026-10-20T10:00:00Z",
    "storyRuns": [
        {
            "id": "run-1",
            "userStoryId": STORY_ID,
            "createdAt": "2026-10-20T10:00:00Z",
            "platforms": [],
        }
    ],
    "targets": [],
}


def _rejection(*codes: str) -> httpx.Response:
    issues = [{"code": code, "message": f"{code} message"} for code in codes]
    return httpx.Response(422, json={"error_code": "build_invalid", "issues": issues})


@pytest.fixture
def api(monkeypatch, tmp_path):
    """Route the CLI's HTTP calls to ``api.respond`` and record every request."""
    settings = Settings(
        api_url="https://testing.example", token="t", app_id="app-123", config_dir=tmp_path
    )
    monkeypatch.setattr(typer.Context, "settings", settings, raising=False)
    monkeypatch.setattr(typer.Context, "json_mode", False, raising=False)
    monkeypatch.setattr(typer.Context, "app_flag", None, raising=False)

    class Api:
        requests: list[httpx.Request] = []
        respond = staticmethod(lambda request: httpx.Response(201, json=BUILD))

    def handle(request: httpx.Request) -> httpx.Response:
        request.read()
        Api.requests.append(request)
        return Api.respond(request)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_client(**kwargs, transport=httpx.MockTransport(handle)),
    )
    Api.requests = []
    return Api


def _form_fields(request: httpx.Request) -> str:
    return request.content.decode("latin-1")


def _stderr(result) -> str:
    return " ".join(result.stderr.split())


class TestUploadPhysical:
    def test_upload_physical_sends_physical_backend(self, api, tmp_path):
        ipa = tmp_path / "App.ipa"
        ipa.write_bytes(b"fake-ipa")

        result = CliRunner().invoke(build_app, ["upload", str(ipa), "--physical"])

        assert result.exit_code == 0, result.output
        body = _form_fields(api.requests[0])
        assert 'name="backend"\r\n\r\nphysical' in body
        assert 'name="platform"\r\n\r\nios' in body
        assert "(ios, physical devices)" in _stderr(result) + result.stdout

    def test_upload_without_flag_sends_no_backend(self, api, tmp_path):
        ipa = tmp_path / "App.ipa"
        ipa.write_bytes(b"fake-ipa")

        result = CliRunner().invoke(build_app, ["upload", str(ipa)])

        assert result.exit_code == 0, result.output
        assert 'name="backend"' not in _form_fields(api.requests[0])

    def test_upload_app_zip_detects_ios(self, api, tmp_path):
        bundle = tmp_path / "App.app.zip"
        bundle.write_bytes(b"fake-zip")

        result = CliRunner().invoke(build_app, ["upload", str(bundle)])

        assert result.exit_code == 0, result.output
        assert 'name="platform"\r\n\r\nios' in _form_fields(api.requests[0])

    def test_device_build_without_flag_points_to_physical(self, api, tmp_path):
        ipa = tmp_path / "App.ipa"
        ipa.write_bytes(b"fake-ipa")
        api.respond = lambda request: _rejection("ios.device_only_ipa", "ios.no_simulator_slice")

        result = CliRunner().invoke(build_app, ["upload", str(ipa)])

        assert result.exit_code == 5
        stderr = _stderr(result)
        assert "failed validation for virtual-device execution" in stderr
        assert "ios.device_only_ipa" in stderr
        assert "minitest build upload <file> --physical" in stderr

    def test_simulator_build_with_flag_points_to_virtual(self, api, tmp_path):
        ipa = tmp_path / "App.ipa"
        ipa.write_bytes(b"fake-ipa")
        api.respond = lambda request: _rejection("ios.simulator_only_ipa")

        result = CliRunner().invoke(build_app, ["upload", str(ipa), "--physical"])

        assert result.exit_code == 5
        stderr = _stderr(result)
        assert "failed validation for physical-device execution" in stderr
        assert "Upload it without --physical" in stderr


class TestRunPhysical:
    @pytest.mark.parametrize(
        "args",
        [["start", STORY_ID, "--no-watch"], ["all"]],
    )
    def test_physical_flags_set_the_target_backend(self, api, args):
        api.respond = lambda request: httpx.Response(200, json=BATCH)

        result = CliRunner().invoke(
            run_app,
            [
                *args,
                "--ios-build",
                "ios-build",
                "--ios-physical",
                "--android-build",
                "android-build",
                "--android-physical",
            ],
        )

        assert result.exit_code == 0, result.output
        assert json.loads(api.requests[0].content)["targets"] == [
            {"platform": "ios", "buildId": "ios-build", "backend": "physical"},
            {"platform": "android", "buildId": "android-build", "backend": "physical"},
        ]

    def test_physical_only_applies_to_its_lane(self, api):
        api.respond = lambda request: httpx.Response(200, json=BATCH)

        result = CliRunner().invoke(
            run_app,
            ["all", "--ios-build", "ios-build", "--ios-physical", "--android-build", "a", "--web"],
        )

        assert result.exit_code == 0, result.output
        assert json.loads(api.requests[0].content)["targets"] == [
            {"platform": "ios", "buildId": "ios-build", "backend": "physical"},
            {"platform": "android", "buildId": "a"},
            {"platform": "web"},
        ]

    @pytest.mark.parametrize("platform", ["ios", "android"])
    def test_physical_rejects_device_type(self, api, platform):
        result = CliRunner().invoke(
            run_app,
            [
                "all",
                f"--{platform}-build",
                "b",
                f"--{platform}-physical",
                f"--{platform}-device-type",
                "tablet",
            ],
        )

        assert result.exit_code == 1
        assert f"--{platform}-physical cannot be combined with --{platform}-device-type" in (
            _stderr(result)
        )
        assert api.requests == []

    def test_physical_requires_its_build(self, api):
        result = CliRunner().invoke(run_app, ["all", "--android-build", "b", "--ios-physical"])

        assert result.exit_code == 1
        assert "--ios-physical requires --ios-build" in _stderr(result)
        assert api.requests == []

    def test_workspace_without_physical_devices_gets_a_clear_error(self, api):
        api.respond = lambda request: httpx.Response(
            403,
            json={
                "error": "forbidden",
                "message": "Physical iOS devices are not enabled for this workspace.",
            },
        )

        result = CliRunner().invoke(run_app, ["all", "--ios-build", "b", "--ios-physical"])

        assert result.exit_code == 3
        stderr = _stderr(result)
        assert "Physical iOS devices are not enabled for this workspace." in stderr
        assert "ask Minitap to enable physical devices" in stderr
        assert "API error" not in stderr
