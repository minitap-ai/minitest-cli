"""`minitest script-runs submit`: run a Maestro or Espresso suite on Minitap devices and wait."""

import asyncio
import io
import time
import zipfile
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import httpx
import typer

from minitest_cli.api.client import UPLOAD_TIMEOUT, ApiClient
from minitest_cli.commands.run_helpers import handle_response_error, resolve_app, run_api_call
from minitest_cli.commands.script_jobs_output import print_failures, result_rows
from minitest_cli.commands.script_runs_helpers import minitap_issue
from minitest_cli.core.config import Settings
from minitest_cli.models.script_run import CreatedScriptJob, ScriptJob
from minitest_cli.utils.output import err_console, output, print_error, print_info, print_table

EXIT_TESTS_FAILED = 1
EXIT_MINITAP_ISSUE = 7
_POLL_S = 5.0
_DONE = {"passed", "failed"}


class Framework(StrEnum):
    maestro = "maestro"
    espresso = "espresso"


def bundle_bytes(tests: Path) -> bytes:
    """A Maestro flows directory zipped as is; a zip or an Espresso test APK sent as it is."""
    if tests.is_file():
        return tests.read_bytes()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(tests.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(tests.parent).as_posix())
    return buffer.getvalue()


def run_link(settings: Settings, app_id: str, run_id: str) -> str:
    return f"{settings.webapp_url.rstrip('/')}/apps/{app_id}/test/script-runs/{run_id}"


def _jobs_path(app_id: str) -> str:
    return f"/api/v1/apps/{app_id}/script-jobs"


def _progress(job: ScriptJob) -> str:
    states = [unit.state for unit in job.units]
    done = sum(state not in ("queued", "running") for state in states)
    failed = sum(state in ("failed", "error") for state in states)
    return (
        f"{done}/{len(states)} done · {states.count('running')} running · "
        f"{states.count('queued')} queued · {failed} failed"
    )


def exit_code(job: ScriptJob) -> int:
    """1 when a test failed; 7 when only Minitap's side kept tests from a verdict; else 0."""
    if any(unit.status == "failed" for unit in job.units):
        return EXIT_TESTS_FAILED
    if job.status == "failed" or any(minitap_issue(unit) for unit in job.units):
        return EXIT_MINITAP_ISSUE
    return 0


async def _submit(
    settings: Settings,
    app_id: str,
    create: dict[str, object],
    bundle: bytes,
    start: dict[str, object],
) -> ScriptJob:
    async with ApiClient(settings) as client:
        resp = await client.post(_jobs_path(app_id), json=create)
        handle_response_error(resp, resource="Script job")
        created = CreatedScriptJob.model_validate(resp.json())
        if len(bundle) > created.max_bundle_bytes:
            print_error(
                f"The test bundle is {len(bundle)} bytes;"
                f" a job takes {created.max_bundle_bytes} at most."
            )
            raise typer.Exit(code=1)
        # The signed storage URL must not carry the Minitest bearer token.
        async with httpx.AsyncClient(timeout=UPLOAD_TIMEOUT) as storage:
            put = await storage.put(
                created.upload_url,
                content=bundle,
                headers={"Content-Type": "application/octet-stream"},
            )
            put.raise_for_status()
        resp = await client.post(f"{_jobs_path(app_id)}/{created.job_id}/start", json=start)
        handle_response_error(resp, resource="Script job")
        return ScriptJob.model_validate(resp.json())


async def _wait(settings: Settings, app_id: str, job: ScriptJob, timeout_s: float) -> ScriptJob:
    deadline = time.monotonic() + timeout_s
    with err_console.status(_progress(job)) as status:
        async with ApiClient(settings) as client:
            while job.status not in _DONE:
                if time.monotonic() > deadline:
                    print_error(
                        f"The job did not finish within {timeout_s:.0f}s; it keeps running."
                    )
                    raise typer.Exit(code=EXIT_MINITAP_ISSUE)
                await asyncio.sleep(_POLL_S)
                resp = await client.get(f"{_jobs_path(app_id)}/{job.job_id}")
                handle_response_error(resp, resource="Script job")
                job = ScriptJob.model_validate(resp.json())
                status.update(_progress(job))
    return job


def submit(
    framework: Annotated[Framework, typer.Option(help="Test framework of the bundle.")],
    tests: Annotated[
        Path,
        typer.Option(
            exists=True,
            help="Maestro flows directory or zip, or the Espresso test APK.",
        ),
    ],
    build_id: Annotated[str, typer.Option("--build-id", help="Native build of the app to test.")],
    model: Annotated[str | None, typer.Option(help="phone (default) or tablet.")] = None,
    os_version: Annotated[
        str | None, typer.Option(help="OS major version, latest by default.")
    ] = None,
    run_name: Annotated[str | None, typer.Option(help="Name of the script run.")] = None,
    commit_sha: Annotated[str | None, typer.Option(help="Commit under test.")] = None,
    branch: Annotated[str | None, typer.Option(help="Branch under test.")] = None,
    wait: Annotated[bool, typer.Option("--wait/--no-wait", help="Wait for the verdict.")] = True,
    timeout: Annotated[float, typer.Option(min=60, help="Seconds to wait for the verdict.")] = 3600,
) -> None:
    """Run a Maestro or Espresso suite on Minitap devices, one device per flow or test class.

    Exits 1 when a test fails, 7 when Minitap could not run some tests (no device, the app did
    not install...), 0 when every test passed.
    """
    settings, app_id, json_mode = resolve_app()
    create = {
        "framework": framework.value,
        "buildId": build_id,
        "model": model,
        "osVersion": os_version,
    }
    start = {"runName": run_name, "commitSha": commit_sha, "branch": branch}
    bundle = bundle_bytes(tests)
    job = run_api_call(
        _submit(
            settings,
            app_id,
            {k: v for k, v in create.items() if v is not None},
            bundle,
            {k: v for k, v in start.items() if v is not None},
        )
    )
    link = run_link(settings, app_id, job.run_id)
    if not json_mode:
        print_info(f"Job {job.job_id}: {len(job.units)} unit(s) on {job.platform} — {link}")
    if wait:
        job = run_api_call(_wait(settings, app_id, job, timeout))
    if json_mode:
        output({**job.model_dump(mode="json", by_alias=True), "runUrl": link}, json_mode=True)
    else:
        if wait:
            print_table(
                ["Unit", "Test", "Status", "Failure", "Minitap issue"],
                result_rows(job.units),
                title=f"{job.run_name} — {job.status}",
            )
            print_failures(job.units)
        print_info(link)
    if wait:
        raise typer.Exit(code=exit_code(job))
