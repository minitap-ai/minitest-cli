"""Script runs: the customer's own suites (Appium hub sessions) that ran on Minitap."""

from datetime import datetime
from typing import Any

from minitest_cli.models.base import CamelModel


class ScriptRunTotals(CamelModel):
    tests: int = 0
    failures: int = 0
    errors: int = 0
    skipped: int = 0
    duration_ms: int | None = None


class ScriptDevice(CamelModel):
    provider: str | None = None
    model: str | None = None
    os_version: str | None = None


class ScriptDeviceTarget(CamelModel):
    """A device (emulator, simulator, physical phone) or, for web, a Minitap browser."""

    platform: str
    backend: str
    model: str | None = None
    os_version: str | None = None
    browser_name: str | None = None
    browser_version: str | None = None
    viewport: str | None = None
    attach_mode: str | None = None
    playwright_version: str | None = None


class ScriptCase(CamelModel):
    position: int
    classname: str | None = None
    name: str
    status: str
    duration_ms: int | None = None
    failure_message: str | None = None
    properties: dict[str, str] | None = None


class ScriptSession(CamelModel):
    scripted_run_id: str
    framework: str
    platform: str | None = None
    status: str
    name: str | None = None
    commit_sha: str | None = None
    device: ScriptDevice | None = None
    external_session_id: str | None = None
    has_video: bool = False
    has_log: bool = False
    started_at: datetime
    finished_at: datetime | None = None
    totals: ScriptRunTotals
    infra_outcome: str | None = None
    infra_detail: str | None = None
    capabilities: dict[str, Any] | None = None
    device_target: ScriptDeviceTarget | None = None
    video_url: str | None = None
    log_url: str | None = None
    driver_log_url: str | None = None
    browser_log_url: str | None = None
    trace_url: str | None = None
    cases: list[ScriptCase] = []


class ScriptRunSummary(CamelModel):
    run_id: str
    run_name: str | None = None
    grouped_by: str
    session_name: str | None = None
    status: str
    frameworks: list[str] = []
    commit_sha: str | None = None
    branch: str | None = None
    pr_number: int | None = None
    session_count: int
    unmarked_session_count: int = 0
    infra_issue_count: int = 0
    totals: ScriptRunTotals
    started_at: datetime
    finished_at: datetime | None = None


class ScriptRunList(CamelModel):
    script_runs: list[ScriptRunSummary]
    total: int


class ScriptRunDetail(ScriptRunSummary):
    sessions: list[ScriptSession] = []


class CreatedScriptJob(CamelModel):
    job_id: str
    upload_url: str
    max_bundle_bytes: int


class ScriptJobUnit(ScriptSession):
    unit: str | None = None
    state: str


class ScriptJob(CamelModel):
    job_id: str
    run_id: str
    run_name: str
    framework: str
    platform: str
    status: str
    units: list[ScriptJobUnit] = []
    # The names of the values passed to the tests; their values are never returned.
    env_keys: list[str] = []
