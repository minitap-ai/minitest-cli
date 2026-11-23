"""'script-runs' against an in-memory testing-service and storage."""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from click import unstyle
from typer.testing import CliRunner

from minitest_cli.commands.script_runs import app as cli
from tests._commit_transport import cli_context, make_settings, routed

runner = CliRunner()
APP_ID = "a0d9820f-5136-4f70-b46b-e5966f56bfb5"
RUN_ID = "632fbbf3-199e-74da-599f-a1da2d6ffa24"
BASE = f"/api/v1/apps/{APP_ID}/script-runs"
STORAGE = "https://storage.example"


def _session(session_id: str, name: str, **fields: Any) -> dict[str, Any]:
    return {
        "scriptedRunId": session_id,
        "framework": "appium",
        "platform": "android",
        "status": "passed",
        "name": name,
        "externalSessionId": f"hub-{session_id}",
        "device": {"provider": "limrun", "model": "Pixel 7", "osVersion": "15"},
        "hasVideo": True,
        "hasLog": True,
        "startedAt": "2026-11-21T16:05:00Z",
        "finishedAt": "2026-11-21T16:06:00Z",
        "totals": {"tests": 1, "failures": 0, "errors": 0, "skipped": 0},
        "videoUrl": f"{STORAGE}/{session_id}/video.mp4?token=signed",
        "logUrl": f"{STORAGE}/{session_id}/appium.log?token=signed",
        "cases": [{"position": 0, "name": name, "status": "passed"}],
        **fields,
    }


SUMMARY: dict[str, Any] = {
    "runId": RUN_ID,
    "runName": "nightly",
    "groupedBy": "runName",
    "status": "failed",
    "frameworks": ["appium"],
    "sessionCount": 3,
    "infraIssueCount": 1,
    "totals": {"tests": 3, "failures": 1, "errors": 0, "skipped": 0},
    "startedAt": "2026-11-21T16:05:00Z",
}
SESSIONS = [
    _session(
        "11111111-1111-4111-8111-111111111111",
        "Sign in",
        device={"provider": "limrun", "model": "limdroid_x86_64_only", "osVersion": "15"},
        deviceTarget={
            "platform": "android",
            "backend": "emulator",
            "model": "tablet",
            "osVersion": "14",
        },
    ),
    _session(
        "22222222-2222-4222-8222-222222222222",
        "Checkout total",
        status="failed",
        cases=[
            {
                "position": 0,
                "name": "Checkout total",
                "status": "failed",
                "failureMessage": "AssertionError: cart $28.99 but checkout $30.49",
            }
        ],
    ),
    _session(
        "33333333-3333-4333-8333-333333333333",
        "Refused",
        status="unmarked",
        infraOutcome="device_unavailable",
        infraDetail="no Android 15 phone emulator was free for this workspace within 60s",
        hasVideo=False,
        hasLog=False,
        videoUrl=None,
        logUrl=None,
        cases=[],
    ),
    _session(
        "44444444-4444-4444-8444-444444444444",
        "Sign in on iPhone",
        platform="ios",
        device={"provider": "limrun", "model": "iPhone 16 Pro", "osVersion": "27.2"},
    ),
]


class FakeTestingService:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.sessions = SESSIONS

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if request.url.host == "storage.example":
            return httpx.Response(200, content=f"bytes of {path}".encode())
        if path == BASE:
            return httpx.Response(200, json={"scriptRuns": [SUMMARY], "total": 1})
        if path == f"{BASE}/{RUN_ID}" and request.url.params.get("format") == "junit":
            return httpx.Response(200, content=b'<testsuites><testsuite name="x"/></testsuites>')
        if path == f"{BASE}/{RUN_ID}":
            return httpx.Response(200, json={**SUMMARY, "sessions": self.sessions})
        return httpx.Response(404, json={"detail": "Script run not found"})


@pytest.fixture
def server() -> FakeTestingService:
    return FakeTestingService()


def _invoke(server: FakeTestingService, tmp_path: Path, *args: str, json_mode: bool = False):
    settings = make_settings(tmp_path, app_id=APP_ID)
    with routed(server.handle), cli_context(settings, json_mode=json_mode):
        return runner.invoke(cli, list(args), env={"COLUMNS": "300"})


def _plain(text: str) -> str:
    return " ".join(unstyle(text).split())


class TestList:
    def test_filters_reach_the_api_and_json_is_the_api_answer(self, server, tmp_path):
        result = _invoke(
            server,
            tmp_path,
            "list",
            "--status",
            "failed",
            "--framework",
            "appium",
            "--search",
            "night",
            json_mode=True,
        )

        assert result.exit_code == 0, result.output
        assert dict(server.requests[0].url.params) == {
            "status": "failed",
            "framework": "appium",
            "search": "night",
            "limit": "25",
            "offset": "0",
        }
        assert json.loads(result.stdout)["scriptRuns"][0]["runId"] == RUN_ID


class TestGet:
    def test_each_test_shows_its_failure_reason_and_minitap_issue(self, server, tmp_path):
        result = _invoke(server, tmp_path, "get", RUN_ID)

        assert result.exit_code == 0, result.output
        table = _plain(result.stdout)
        assert "AssertionError: cart $28.99 but checkout $30.49" in table
        assert "device_unavailable: no Android 15 phone emulator was free" in table
        assert "Pixel 7 · Android 15" in table
        assert "Tablet emulator · Android 14" in table
        assert "limdroid" not in table

    def test_each_test_shows_its_platform_and_platform_keeps_only_its_tests(self, server, tmp_path):
        everything = _plain(_invoke(server, tmp_path, "get", RUN_ID).stdout)
        ios = _invoke(server, tmp_path, "get", RUN_ID, "--platform", "ios", json_mode=True)

        assert "Sign in on iPhone │ iOS │ passed │ iPhone 16 Pro simulator · iOS 27.2" in everything
        assert "Sign in │ Android │ passed │ Tablet emulator · Android 14" in everything
        assert ios.exit_code == 0, ios.output
        sessions = json.loads(ios.stdout)["sessions"]
        assert [(s["name"], s["platform"]) for s in sessions] == [("Sign in on iPhone", "ios")]

    def test_a_test_on_android_and_iphone_is_one_line_with_each_device_status(
        self, server, tmp_path
    ):
        server.sessions = [
            _session("55555555-5555-4555-8555-555555555555", "Checkout total"),
            _session(
                "66666666-6666-4666-8666-666666666666",
                "Checkout total",
                platform="ios",
                status="failed",
                device={"provider": "limrun", "model": "iPhone 16 Pro", "osVersion": "27.2"},
                cases=[
                    {
                        "position": 0,
                        "name": "Checkout total",
                        "status": "failed",
                        "failureMessage": "no Pay button",
                    }
                ],
            ),
        ]

        table = _plain(_invoke(server, tmp_path, "get", RUN_ID).stdout)
        tests = json.loads(_invoke(server, tmp_path, "get", RUN_ID, json_mode=True).stdout)["tests"]

        assert "Tests (1)" in table
        assert "Pixel 7 · Android 15: passed" in table
        assert "iPhone 16 Pro simulator · iOS 27.2: failed" in table
        assert [(t["name"], t["status"], len(t["devices"])) for t in tests] == [
            ("Checkout total", "failed", 2)
        ]
        assert tests[0]["devices"][1]["failure"] == "no Pay button"

    def test_a_tests_devices_read_android_first_whatever_order_they_ran(self, server, tmp_path):
        server.sessions = [
            _session("77777777-7777-4777-8777-777777777777", "Sign in", platform="ios"),
            _session("88888888-8888-4888-8888-888888888888", "Sign in"),
        ]

        tests = json.loads(_invoke(server, tmp_path, "get", RUN_ID, json_mode=True).stdout)["tests"]

        assert [d["platform"] for d in tests[0]["devices"]] == ["android", "ios"]

    def test_unknown_run_says_runs_are_kept_90_days(self, server, tmp_path):
        result = _invoke(server, tmp_path, "get", "00000000-0000-4000-8000-000000000000")

        assert result.exit_code == 4
        assert "script runs are kept 90 days" in _plain(result.stderr)


class TestDownloads:
    def test_recording_of_a_named_test_comes_from_storage_without_the_minitest_token(
        self, server, tmp_path
    ):
        out = tmp_path / "checkout.mp4"

        result = _invoke(
            server, tmp_path, "recording", RUN_ID, "--test", "Checkout total", "--out", str(out)
        )

        assert result.exit_code == 0, result.output
        assert out.read_bytes() == b"bytes of /22222222-2222-4222-8222-222222222222/video.mp4"
        storage_request = server.requests[-1]
        assert storage_request.url.host == "storage.example"
        assert "authorization" not in storage_request.headers

    def test_a_run_of_several_tests_needs_test_and_lists_them(self, server, tmp_path):
        result = _invoke(server, tmp_path, "appium-log", RUN_ID)

        assert result.exit_code == 1
        assert "This run has 4 tests; pick one with --test" in _plain(result.stderr)
        assert "Checkout total" in result.stderr

    def test_missing_appium_log_names_its_retention(self, server, tmp_path):
        result = _invoke(server, tmp_path, "appium-log", RUN_ID, "--test", "Refused")

        assert result.exit_code == 4
        assert "Appium logs are kept 30 days" in _plain(result.stderr)
        assert not (tmp_path / "minitest-script-runs").exists()

    def test_junit_is_written_as_the_api_returns_it(self, server, tmp_path):
        out = tmp_path / "report.xml"

        result = _invoke(server, tmp_path, "junit", RUN_ID, "--out", str(out))

        assert result.exit_code == 0, result.output
        assert out.read_bytes() == b'<testsuites><testsuite name="x"/></testsuites>'


def _web_session(session_id: str, name: str, browser: str, version: str, **fields: Any):
    return _session(
        session_id,
        name,
        framework="playwright",
        platform="web",
        device=None,
        deviceTarget={
            "platform": "web",
            "backend": "browser",
            "browserName": browser,
            "browserVersion": version,
            "viewport": "1280x800",
            "attachMode": "connect",
            "playwrightVersion": "1.65",
        },
        traceUrl=f"{STORAGE}/{session_id}/trace.zip?token=signed",
        browserLogUrl=f"{STORAGE}/{session_id}/browser-log.json?token=signed",
        driverLogUrl=None,
        **fields,
    )


class TestWeb:
    def test_a_playwright_test_lists_each_browser_it_ran_on(self, server, tmp_path):
        server.sessions = [
            _web_session(
                "99999999-9999-4999-8999-999999999999", "checkout › pays", "chrome", "157"
            ),
            _web_session(
                "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                "checkout › pays",
                "firefox",
                "159",
                status="failed",
            ),
            SESSIONS[0],
        ]

        table = _plain(_invoke(server, tmp_path, "get", RUN_ID).stdout)
        web = json.loads(
            _invoke(server, tmp_path, "get", RUN_ID, "--platform", "web", json_mode=True).stdout
        )

        assert "Chrome 157 · 1280×800: passed" in table
        assert "Firefox 159 · 1280×800: failed" in table
        assert [d["device"] for d in web["tests"][0]["devices"]] == [
            "Chrome 157 · 1280×800",
            "Firefox 159 · 1280×800",
        ]
        assert {s["platform"] for s in web["sessions"]} == {"web"}

    def test_trace_and_browser_log_download_from_storage(self, server, tmp_path):
        session_id = "99999999-9999-4999-8999-999999999999"
        server.sessions = [_web_session(session_id, "checkout › pays", "chrome", "157")]
        trace, log = tmp_path / "t.zip", tmp_path / "b.json"

        traced = _invoke(server, tmp_path, "trace", RUN_ID, "--out", str(trace))
        logged = _invoke(server, tmp_path, "browser-log", RUN_ID, "--out", str(log))
        driver = _invoke(server, tmp_path, "driver-log", RUN_ID)

        assert (traced.exit_code, logged.exit_code) == (0, 0), traced.output + logged.output
        assert trace.read_bytes() == f"bytes of /{session_id}/trace.zip".encode()
        assert log.read_bytes() == f"bytes of /{session_id}/browser-log.json".encode()
        assert driver.exit_code == 4
        assert "logs and traces are kept 30 days" in _plain(driver.stderr)
