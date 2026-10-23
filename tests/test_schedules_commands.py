"""`minitest schedules`, driven against an in-memory fake of the testing-service schedules API."""

import json
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from minitest_cli.commands import schedules
from tests._commit_transport import cli_context, make_settings, routed

runner = CliRunner()

APP = "a0d9820f-5136-4f70-b46b-e5966f56bfb5"
SCHEDULES = f"/api/v1/apps/{APP}/schedules"
TAG_ID = "7d0c1f8e-3a52-4c55-9d4e-0d8f1d2a9c01"
DEALS_ID = "5c4ed000-0000-4000-8000-000000010002"
BUILD_ID = "5c4ed000-0000-4000-8000-00000000b001"
SAVED_ID = "27040426-7ec3-4995-ab66-26d73ae719da"
BATCH_ID = "9b1f7a6e-2c1d-4b8e-8a57-3f0e5c2d1a10"

WEB_TARGET = {"platform": "web", "browser": "chrome", "viewport": "pc"}
SAVED = {
    "id": SAVED_ID,
    "appId": APP,
    "tenantId": "5c4ed000-0000-4000-8000-000000000001",
    "name": "Nightly sanity check",
    "scope": {"mode": "suite"},
    "targets": [WEB_TARGET],
    "webSource": {"mode": "url", "url": "https://startsiden.example.com"},
    "buildSources": None,
    "timeOfDay": "03:00:00",
    "days": [0, 1, 2, 3, 4],
    "timezone": "Europe/Oslo",
    "slackChannelId": "C0MINITAP",
    "slackChannelName": "minitap",
    "postAllClear": True,
    "paused": False,
    "createdAt": "2026-10-20T10:00:00Z",
    "updatedAt": "2026-10-20T10:00:00Z",
    "nextRunAt": "2026-10-26T02:00:00Z",
    "scenarioCount": 9,
    "etaSeconds": 960,
}


def _fire(**fields: Any) -> dict[str, Any]:
    base = {
        "id": "f1",
        "scheduleId": SAVED_ID,
        "scheduledFor": "2026-10-23T01:00:00Z",
        "status": "started",
        "batchId": BATCH_ID,
        "skipReason": None,
        "slackChannelId": "C0MINITAP",
        "slackChannelName": "minitap",
        "createdAt": "2026-10-23T01:00:00Z",
    }
    return {**base, **fields}


class FakeBackend:
    def __init__(self, *, routes: bool = True) -> None:
        self.routes = routes
        self.schedules = [dict(SAVED)]
        self.fires: list[dict[str, Any]] = []
        self.run_now = _fire()
        self.requests: list[httpx.Request] = []

    def sent(self, method: str, path: str) -> list[dict[str, Any]]:
        return [
            json.loads(r.content) if r.content else {}
            for r in self.requests
            if r.method == method and r.url.path == path
        ]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path, method = request.url.path, request.method
        if path == f"/api/v1/apps/{APP}/tags":
            return httpx.Response(200, json=[{"id": TAG_ID, "name": "Navigation"}])
        if path == f"/api/v1/apps/{APP}/user-stories":
            items = [{"id": DEALS_ID, "name": "Deals page opens"}]
            return httpx.Response(200, json={"items": items, "total": 1})
        if not self.routes:
            return httpx.Response(404, json={"error": "not_found", "message": "Not Found"})
        if path == SCHEDULES and method == "GET":
            return httpx.Response(200, json=self.schedules)
        if path == SCHEDULES and method == "POST":
            created = {**SAVED, **json.loads(request.content), "id": "new-id"}
            self.schedules.append(created)
            return httpx.Response(201, json=created)
        if path == f"{SCHEDULES}/preview":
            return httpx.Response(200, json={"scenarioCount": 1, "etaSeconds": 60, "lanes": []})
        if path == f"{SCHEDULES}/{SAVED_ID}" and method == "PATCH":
            self.schedules[0] = {**self.schedules[0], **json.loads(request.content)}
            return httpx.Response(200, json=self.schedules[0])
        if path == f"{SCHEDULES}/{SAVED_ID}" and method == "DELETE":
            self.schedules.pop(0)
            return httpx.Response(204)
        if path == f"{SCHEDULES}/{SAVED_ID}/run-now":
            return httpx.Response(200, json=self.run_now)
        if path == f"{SCHEDULES}/{SAVED_ID}/fires":
            return httpx.Response(200, json=self.fires)
        return httpx.Response(404, json={"error": "not_found", "message": "Schedule not found"})


def _invoke(tmp_path, backend: FakeBackend, args: list[str], *, json_mode: bool = False):
    with cli_context(make_settings(tmp_path), json_mode=json_mode), routed(backend):
        return runner.invoke(schedules.app, args)


class TestCreate:
    def test_flags_become_the_schedule_the_api_stores(self, tmp_path):
        backend = FakeBackend()

        result = _invoke(
            tmp_path,
            backend,
            [
                "create", "--name", "cli nightly", "--at", "3:00", "--timezone", "Europe/Oslo",
                "--tag", "navigation", "--exclude", "Deals page opens",
                "--url", "https://startsiden.example.com", "--browser", "chrome",
                "--browser", "chrome:android", "--android-build", BUILD_ID,
                "--slack-channel", "C0MINITAP", "--slack-channel-name", "#minitap",
            ],
        )  # fmt: skip

        assert result.exit_code == 0, result.output
        assert backend.sent("POST", SCHEDULES) == [
            {
                "name": "cli nightly",
                "timeOfDay": "03:00",
                "days": [0, 1, 2, 3, 4],
                "timezone": "Europe/Oslo",
                "slackChannelId": "C0MINITAP",
                "slackChannelName": "minitap",
                "scope": {"mode": "tags", "tagIds": [TAG_ID], "excludedIds": [DEALS_ID]},
                "targets": [
                    WEB_TARGET,
                    {"platform": "android", "browser": "chrome"},
                    {"platform": "android", "backend": "cloud"},
                ],
                "webSource": {"mode": "url", "url": "https://startsiden.example.com"},
                "buildSources": {"android": {"mode": "fixed", "buildId": BUILD_ID}},
            }
        ]
        assert "Schedule created: cli nightly" in result.stderr

    def test_from_file_accepts_get_json_output_and_flags_override_it(self, tmp_path):
        backend = FakeBackend()
        spec = tmp_path / "schedule.yaml"
        spec.write_text(
            "id: old-id\nnextRunAt: '2026-10-26T02:00:00Z'\nname: copied\ntimeOfDay: 03:00\n"
            "timezone: Europe/Oslo\nscope: {mode: suite}\n"
            "targets: [{platform: ios, backend: cloud}]\nbuildSources: {ios: {mode: latest}}\n"
            "slackChannelId: C0MINITAP\nslackChannelName: minitap\n"
        )

        result = _invoke(
            tmp_path, backend, ["create", "--from-file", str(spec), "--name", "cli copy"]
        )

        assert result.exit_code == 0, result.output
        [posted] = backend.sent("POST", SCHEDULES)
        assert posted["name"] == "cli copy"
        assert posted["timeOfDay"] == "03:00"
        assert posted["targets"] == [{"platform": "ios", "backend": "cloud"}]
        assert "id" not in posted and "nextRunAt" not in posted

    def test_timezone_defaults_to_the_machine_timezone(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TZ", "Asia/Tokyo")
        backend = FakeBackend()

        result = _invoke(
            tmp_path,
            backend,
            ["create", "--name", "n", "--at", "03:00", "--ios", "--slack-channel", "C1"],
        )

        assert result.exit_code == 0, result.output
        assert backend.sent("POST", SCHEDULES)[0]["timezone"] == "Asia/Tokyo"

    @pytest.mark.parametrize(
        "flags",
        [
            ["--at", "25:00"],
            ["--at", "03:00", "--timezone", "Mars/Base"],
            ["--at", "03:00", "--days", "funday"],
            ["--at", "03:00", "--browser", "chrome"],
        ],
    )
    def test_invalid_input_is_rejected_before_any_request(self, tmp_path, flags):
        backend = FakeBackend()

        result = _invoke(
            tmp_path, backend, ["create", "--name", "n", "--slack-channel", "C1", *flags]
        )

        assert result.exit_code == 1
        assert backend.requests == []


class TestUpdate:
    def test_a_native_flag_redefines_only_that_platform(self, tmp_path):
        backend = FakeBackend()

        result = _invoke(
            tmp_path, backend, ["update", "nightly sanity check", "--android-branch", "main"]
        )

        assert result.exit_code == 0, result.output
        assert backend.sent("PATCH", f"{SCHEDULES}/{SAVED_ID}") == [
            {
                "targets": [WEB_TARGET, {"platform": "android", "backend": "cloud"}],
                "webSource": SAVED["webSource"],
                "buildSources": {"android": {"mode": "branch", "branch": "main"}},
            }
        ]

    def test_nothing_to_change_never_patches(self, tmp_path):
        backend = FakeBackend()

        result = _invoke(tmp_path, backend, ["update", SAVED_ID])

        assert result.exit_code == 1
        assert backend.sent("PATCH", f"{SCHEDULES}/{SAVED_ID}") == []

    def test_pause_then_resume(self, tmp_path):
        backend = FakeBackend()

        paused = _invoke(tmp_path, backend, ["pause", "Nightly sanity check"])
        resumed = _invoke(tmp_path, backend, ["resume", SAVED_ID])

        assert paused.exit_code == resumed.exit_code == 0
        assert backend.sent("PATCH", f"{SCHEDULES}/{SAVED_ID}") == [
            {"paused": True},
            {"paused": False},
        ]
        assert "Status:     Paused" in paused.stdout
        assert "Status:     On" in resumed.stdout


class TestDeleteAndRun:
    def test_delete_requires_yes(self, tmp_path):
        backend = FakeBackend()

        refused = _invoke(tmp_path, backend, ["delete", "Nightly sanity check"])
        deleted = _invoke(tmp_path, backend, ["delete", "Nightly sanity check", "--yes"])

        assert refused.exit_code == 1
        assert deleted.exit_code == 0, deleted.output
        assert len(backend.sent("DELETE", f"{SCHEDULES}/{SAVED_ID}")) == 1
        assert backend.schedules == []

    def test_run_now_that_cannot_start_says_why(self, tmp_path):
        backend = FakeBackend()
        backend.run_now = _fire(status="skipped", batchId=None, skipReason="no_build")

        result = _invoke(tmp_path, backend, ["run", "Nightly sanity check"])

        assert result.exit_code == 0, result.output
        assert "Didn't run: no installable build" in result.stderr


class TestFires:
    def test_each_night_shows_its_verdict_or_why_it_did_not_run(self, tmp_path, monkeypatch):
        monkeypatch.setenv("COLUMNS", "250")
        backend = FakeBackend()
        issues = [
            {"issueId": "i1", "title": "Deals 404", "criticality": "critical", "isNew": True},
            {"issueId": "i2", "title": "Offline", "criticality": "warning", "isNew": False},
            {"issueId": "i3", "title": "Search", "criticality": "warning", "isNew": False},
        ]
        summary = {
            "outcome": "critical",
            "passed": 15,
            "total": 18,
            "unchecked": 0,
            "issues": issues,
            "testedBuilds": [],
            "testedUrl": "https://startsiden.example.com",
            "testedUrlIsNew": False,
        }
        backend.fires = [
            _fire(summary=summary),
            _fire(status="skipped", batchId=None, skipReason="out_of_credits"),
        ]

        result = _invoke(tmp_path, backend, ["fires", "Nightly sanity check"])

        assert result.exit_code == 0, result.output
        night, skipped = [line for line in result.stdout.splitlines() if "Fri 23 Oct" in line]
        assert [cell.strip() for cell in night.split("│")[2:6]] == ["critical", "15/18", "1", "2"]
        assert "Didn't run: the workspace ran out of credits" in skipped


class TestBackendErrors:
    def test_backend_without_schedules_says_it_is_not_available(self, tmp_path):
        result = _invoke(tmp_path, FakeBackend(routes=False), ["list"])

        assert result.exit_code == 4
        assert "Scheduled runs are not available on this workspace yet." in result.stderr
        assert "Traceback" not in result.output

    def test_unknown_schedule_id_is_a_plain_not_found(self, tmp_path):
        result = _invoke(tmp_path, FakeBackend(), ["restore", "nope"])

        assert result.exit_code == 4
        assert "Schedule not found" in result.stderr
