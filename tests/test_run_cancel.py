"""`minitest run cancel` against a fake testing-service speaking real HTTP."""

import json
import re
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from minitest_cli.commands.run import app as run_app
from tests._commit_transport import cli_context, make_settings, routed

RUN_ID = "11111111-2222-3333-4444-555555555555"
IOS_SRP = "aaaaaaaa-0000-0000-0000-000000000001"
ANDROID_SRP = "aaaaaaaa-0000-0000-0000-000000000002"
WEB_SRP = "aaaaaaaa-0000-0000-0000-000000000003"
FINISHED = {"evaluating", "completed", "failed", "skipped", "escalated"}
SRP_CANCEL = re.compile(r"/api/v1/apps/[^/]+/story-run-platforms/([^/]+)/cancel$")

runner = CliRunner()


class FakeTestingService:
    """Implements the story-run GET and the per-SRP cancel route like testing-service."""

    def __init__(self, states: dict[str, str]) -> None:
        self.platforms = [
            {
                "platform": name,
                "srpId": srp,
                "executionState": state,
                "cancellationRequestedAt": None,
            }
            for name, srp, state in (
                ("ios", IOS_SRP, states.get("ios")),
                ("android", ANDROID_SRP, states.get("android")),
                ("web", WEB_SRP, states.get("web")),
            )
            if state is not None
        ]
        self.cancel_calls: list[str] = []

    def run(self) -> dict[str, Any]:
        return {
            "id": RUN_ID,
            "userStoryId": "us-1",
            "createdAt": "2026-10-05T10:00:00Z",
            "platforms": self.platforms,
        }

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "GET" and path.endswith(f"/story-runs/{RUN_ID}"):
            return httpx.Response(200, json=self.run())
        match = SRP_CANCEL.search(path)
        if request.method == "POST" and match:
            srp_id = match.group(1)
            self.cancel_calls.append(srp_id)
            platform = next(p for p in self.platforms if p["srpId"] == srp_id)
            if platform["executionState"] in FINISHED:
                return httpx.Response(409, json={"detail": "already terminal"})
            platform["cancellationRequestedAt"] = "2026-10-05T10:01:00Z"
            return httpx.Response(200, json=self.run())
        return httpx.Response(404, json={"detail": "Not Found"})


@pytest.fixture
def invoke(tmp_path):
    def _invoke(server: Callable[[httpx.Request], httpx.Response], *args: str, json_mode=False):
        with routed(server), cli_context(make_settings(tmp_path), json_mode=json_mode):
            return runner.invoke(run_app, ["cancel", *args])

    return _invoke


class TestRunCancel:
    def test_cancel_cancels_only_unfinished_platforms(self, invoke) -> None:
        server = FakeTestingService({"ios": "running", "android": "pending", "web": "completed"})

        result = invoke(server, RUN_ID, json_mode=True)

        assert result.exit_code == 0, result.output
        assert server.cancel_calls == [IOS_SRP, ANDROID_SRP]
        payload = json.loads(result.stdout)
        stamped = {p["platform"]: p["cancellationRequestedAt"] for p in payload["platforms"]}
        assert stamped["ios"] is not None
        assert stamped["android"] is not None
        assert stamped["web"] is None

    def test_cancel_human_output_names_cancelled_platforms(self, invoke) -> None:
        server = FakeTestingService({"ios": "running", "android": "completed"})

        result = invoke(server, RUN_ID)

        assert result.exit_code == 0, result.output
        assert f"Run cancelled: {RUN_ID} (ios; status: cancelled)" in result.output

    @pytest.mark.parametrize(
        ("args", "expected_calls"),
        [
            (["--platform", "android"], [ANDROID_SRP]),
            (["--srp", IOS_SRP], [IOS_SRP]),
        ],
    )
    def test_cancel_honours_platform_filters(self, invoke, args, expected_calls) -> None:
        server = FakeTestingService({"ios": "running", "android": "running"})

        result = invoke(server, RUN_ID, *args)

        assert result.exit_code == 0, result.output
        assert server.cancel_calls == expected_calls

    def test_cancel_all_finished_exits_1_without_cancelling(self, invoke) -> None:
        server = FakeTestingService({"ios": "completed", "android": "failed"})

        result = invoke(server, RUN_ID)

        assert result.exit_code == 1
        assert server.cancel_calls == []
        assert "Nothing to cancel" in result.output
        assert "ios: completed, android: failed" in " ".join(result.output.split())

    def test_cancel_platform_finishing_mid_request_counts_as_nothing_cancelled(
        self, invoke
    ) -> None:
        server = FakeTestingService({"ios": "running"})
        original = server.__call__

        def race(request: httpx.Request) -> httpx.Response:
            if request.method == "POST":
                server.platforms[0]["executionState"] = "completed"
            return original(request)

        result = invoke(race, RUN_ID)

        assert result.exit_code == 1
        assert "Nothing to cancel" in result.output

    def test_cancel_missing_platform_exits_4(self, invoke) -> None:
        server = FakeTestingService({"ios": "running"})

        result = invoke(server, RUN_ID, "--platform", "web")

        assert result.exit_code == 4
        assert server.cancel_calls == []

    def test_cancel_unknown_run_exits_4(self, invoke) -> None:
        server = FakeTestingService({"ios": "running"})

        result = invoke(server, "deadbeef-dead-beef-dead-beefdeadbeef")

        assert result.exit_code == 4
