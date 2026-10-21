"""`minitest run logs` against a fake testing-service and storage speaking real HTTP."""

import gzip
import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from minitest_cli.commands.run import app as run_app
from tests._commit_transport import cli_context, make_settings, routed

RUN_ID = "11111111-2222-3333-4444-555555555555"
ANDROID_SRP = "aaaaaaaa-0000-0000-0000-000000000002"
IOS_SRP = "aaaaaaaa-0000-0000-0000-000000000001"
LOGCAT = "10-20 16:00:03.000  4242  4242 E AndroidRuntime: FATAL EXCEPTION: main\n"
REPORT = "10-20 16:00:03.000  4242  4242 E AndroidRuntime: at Pay.run(Pay.kt:118)\n"

runner = CliRunner()


class FakeServices:
    def __init__(self, lane_logs: dict[str, Any] | None) -> None:
        self.lane_logs = lane_logs
        self.asked_srps: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith(f"/story-runs/{RUN_ID}"):
            return httpx.Response(200, json=_run())
        if path.endswith(f"/story-runs/{RUN_ID}/lane-logs"):
            self.asked_srps.append(request.url.params["srp_id"])
            if self.lane_logs is None:
                return httpx.Response(404, json={"detail": "Story run not found"})
            return httpx.Response(200, json=self.lane_logs)
        if request.url.host == "storage.test":
            body = {"/device.log.gz": gzip.compress(LOGCAT.encode()), "/crash.txt": REPORT}
            return httpx.Response(200, content=body[path])
        return httpx.Response(404)


def _run() -> dict[str, Any]:
    return {
        "id": RUN_ID,
        "userStoryId": "us-1",
        "createdAt": "2026-10-05T10:00:00Z",
        "platforms": [
            {"platform": "ios", "srpId": IOS_SRP, "executionState": "completed"},
            {"platform": "android", "srpId": ANDROID_SRP, "executionState": "failed"},
        ],
    }


CRASHED = {
    "status": "ready",
    "files": [
        {
            "kind": "device_log",
            "fileName": "device.log",
            "bytes": len(LOGCAT),
            "compressed": True,
            "url": "https://storage.test/device.log.gz",
        },
        {
            "kind": "crash_report",
            "fileName": "crash-report.txt",
            "bytes": len(REPORT),
            "compressed": False,
            "url": "https://storage.test/crash.txt",
        },
    ],
    "crashes": [
        {
            "kind": "exception",
            "title": "java.lang.NullPointerException",
            "frame": "at Pay.run(Pay.kt:118)",
            "summary": "NullPointerException in Pay.kt:118",
            "offsetMs": 52300,
        }
    ],
}


@pytest.fixture
def invoke(tmp_path):
    def _invoke(server: Callable[[httpx.Request], httpx.Response], *args: str, json_mode=False):
        with routed(server), cli_context(make_settings(tmp_path), json_mode=json_mode):
            return runner.invoke(run_app, ["logs", RUN_ID, *args])

    return _invoke


class TestRunLogs:
    def test_logs_writes_the_target_files_decompressed(self, invoke, tmp_path) -> None:
        server = FakeServices(CRASHED)

        result = invoke(server, "--platform", "android", "--out", str(tmp_path / "out"))

        assert result.exit_code == 0, result.output
        assert server.asked_srps == [ANDROID_SRP]
        assert (tmp_path / "out" / "device.log").read_text() == LOGCAT
        assert (tmp_path / "out" / "crash-report.txt").read_text() == REPORT
        assert not list((tmp_path / "out").glob("*.gz"))
        assert "NullPointerException in Pay.kt:118" in result.output
        assert "0:52.3" in result.output

    def test_logs_json_lists_written_files_and_crashes(self, invoke, tmp_path) -> None:
        result = invoke(
            FakeServices(CRASHED),
            "--platform",
            "android",
            "--out",
            str(tmp_path / "out"),
            json_mode=True,
        )

        payload = json.loads(result.stdout)
        assert [(f["kind"], f["bytes"]) for f in payload["files"]] == [
            ("device_log", len(LOGCAT)),
            ("crash_report", len(REPORT)),
        ]
        assert payload["crashes"][0]["offsetMs"] == 52300

    @pytest.mark.parametrize(
        ("lane_logs", "exit_code", "message"),
        [
            ({"status": "pending", "files": [], "crashes": []}, 1, "still running"),
            ({"status": "none", "files": [], "crashes": []}, 4, "No logs were captured"),
            (None, 4, "aren't enabled"),
        ],
    )
    def test_logs_explains_a_target_without_files(
        self, invoke, lane_logs, exit_code: int, message: str
    ) -> None:
        result = invoke(FakeServices(lane_logs), "--platform", "ios")

        assert result.exit_code == exit_code
        assert message in result.output
