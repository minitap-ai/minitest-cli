"""'script-runs submit' against an in-memory testing-service and storage."""

import io
import json
import zipfile
from pathlib import Path
from typing import Any

import httpx
import pytest
from click import unstyle
from typer.testing import CliRunner

from minitest_cli.commands import script_jobs
from minitest_cli.commands.script_runs import app as cli
from tests._commit_transport import cli_context, make_settings, routed

runner = CliRunner()
APP_ID = "a0d9820f-5136-4f70-b46b-e5966f56bfb5"
JOB_ID = "edfe612f-a82b-471b-9a3f-1faa43c2404a"
RUN_ID = "6e999210-a9d9-7457-0f8f-ea048a7d5320"
BASE = f"/api/v1/apps/{APP_ID}/script-jobs"
UPLOAD = "https://storage.example/upload/bundle?token=signed"


def _unit(name: str, state: str, failure: str | None = None) -> dict[str, Any]:
    finished = state not in ("queued", "running")
    cases = (
        [{"position": 0, "name": name, "status": state, "failureMessage": failure}]
        if finished
        else []
    )
    return {
        "scriptedRunId": f"unit-{name}",
        "framework": "maestro",
        "platform": "android",
        "status": state if finished else "running",
        "name": name,
        "startedAt": "2026-11-22T21:00:00Z",
        "totals": {"tests": len(cases), "failures": 0, "errors": 0, "skipped": 0},
        "cases": cases,
        "unit": f"flows/{name}.yaml",
        "state": state,
    }


def _job(status: str, units: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "jobId": JOB_ID,
        "runId": RUN_ID,
        "runName": "nightly",
        "framework": "maestro",
        "platform": "android",
        "status": status,
        "units": units,
    }


class FakeJobs:
    def __init__(self, polls: list[dict[str, Any]]) -> None:
        self.polls = polls
        self.requests: list[httpx.Request] = []
        self.bundle: bytes | None = None
        self.created: dict[str, Any] | None = None
        self.started: dict[str, Any] | None = None

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.host == "storage.example":
            self.bundle = request.content
            return httpx.Response(200)
        if request.method == "POST" and request.url.path == BASE:
            self.created = json.loads(request.content)
            return httpx.Response(
                201, json={"jobId": JOB_ID, "uploadUrl": UPLOAD, "maxBundleBytes": 1_000_000}
            )
        if request.url.path == f"{BASE}/{JOB_ID}/start":
            self.started = json.loads(request.content)
            return httpx.Response(200, json=_job("queued", [_unit("a", "queued")]))
        if request.url.path == f"{BASE}/{JOB_ID}":
            return httpx.Response(200, json=self.polls.pop(0))
        return httpx.Response(404, json={"detail": "not found"})


@pytest.fixture(autouse=True)
def _no_wait_between_polls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(script_jobs, "_POLL_S", 0)


@pytest.fixture
def flows(tmp_path: Path) -> Path:
    folder = tmp_path / "flows"
    folder.mkdir()
    (folder / "config.yaml").write_text('flows: ["0*.yaml"]\n')
    (folder / "01_sign_in.yaml").write_text("appId: com.food\n---\n- launchApp\n")
    return folder


def _submit(server: FakeJobs, tmp_path: Path, tests: Path, *extra: str, json_mode: bool = False):
    settings = make_settings(tmp_path, app_id=APP_ID)
    args = ["submit", "--framework", "maestro", "--tests", str(tests)]
    args += ["--build-id", "857a4e52-a8eb-4bab-90e2-a23a4218da0e", *extra]
    with routed(server.handle), cli_context(settings, json_mode=json_mode):
        return runner.invoke(cli, args, env={"COLUMNS": "300"})


def test_a_flows_folder_is_zipped_uploaded_to_storage_and_started(flows, tmp_path):
    server = FakeJobs([_job("passed", [_unit("a", "passed")])])

    result = _submit(server, tmp_path, flows, "--run-name", "nightly", "--commit-sha", "a" * 40)

    assert result.exit_code == 0, result.output
    assert server.created == {
        "framework": "maestro",
        "buildId": "857a4e52-a8eb-4bab-90e2-a23a4218da0e",
    }
    assert server.started == {"runName": "nightly", "commitSha": "a" * 40}
    assert server.bundle is not None
    names = zipfile.ZipFile(io.BytesIO(server.bundle)).namelist()
    assert sorted(names) == ["flows/01_sign_in.yaml", "flows/config.yaml"]
    upload = next(r for r in server.requests if r.url.host == "storage.example")
    assert upload.method == "PUT" and "authorization" not in upload.headers
    assert f"/test/script-runs/{RUN_ID}" in unstyle(result.stderr)


def test_a_failing_test_exits_1_with_its_reason(flows, tmp_path):
    failed = _unit("checkout", "failed", 'Assertion is false: "$28.99" is visible')
    server = FakeJobs(
        [
            _job("running", [_unit("a", "passed"), _unit("checkout", "running")]),
            _job("failed", [_unit("a", "passed"), failed]),
        ]
    )

    result = _submit(server, tmp_path, flows)

    assert result.exit_code == 1, result.output
    assert 'Assertion is false: "$28.99" is visible' in " ".join(unstyle(result.stdout).split())


def test_a_unit_minitap_could_not_run_exits_7(flows, tmp_path):
    refused = {
        **_unit("a", "error"),
        "status": "unmarked",
        "cases": [],
        "infraOutcome": "device_unavailable",
        "infraDetail": "no device",
    }
    server = FakeJobs([_job("failed", [refused])])

    result = _submit(server, tmp_path, flows)

    assert result.exit_code == 7, result.output


def test_no_wait_returns_the_job_and_its_run_link_at_once(flows, tmp_path):
    server = FakeJobs([])

    result = _submit(server, tmp_path, flows, "--no-wait", json_mode=True)

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert (payload["jobId"], payload["status"]) == (JOB_ID, "queued")
    assert payload["runUrl"].endswith(f"/apps/{APP_ID}/test/script-runs/{RUN_ID}")
    assert not any(r.method == "GET" for r in server.requests)


def test_an_espresso_test_apk_is_sent_as_it_is(tmp_path):
    apk = tmp_path / "app-test.apk"
    apk.write_bytes(b"PK\x03\x04 test apk")
    server = FakeJobs([_job("passed", [_unit("a", "passed")])])

    result = _submit(server, tmp_path, apk)

    assert result.exit_code == 0, result.output
    assert server.bundle == b"PK\x03\x04 test apk"
