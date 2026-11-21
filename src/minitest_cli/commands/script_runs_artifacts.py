"""Downloads of a script run: a test's recording and Appium log, the run's JUnit report."""

from pathlib import Path
from typing import Annotated

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.run_helpers import (
    EXIT_NOT_FOUND,
    ensure_uuid,
    handle_response_error,
    resolve_app,
    run_api_call,
)
from minitest_cli.commands.run_recording_helpers import download
from minitest_cli.commands.script_runs_helpers import (
    RUN_RETENTION,
    fetch_run,
    pick_test,
    script_runs_path,
    test_label,
)
from minitest_cli.models.script_run import ScriptSession
from minitest_cli.utils.output import print_error, print_json, print_success

RunArg = Annotated[str, typer.Argument(help="Script run ID.")]
TestOpt = Annotated[
    str | None,
    typer.Option(
        "--test", help="Test ID, hub session ID or name; needed when the run has several."
    ),
]
OutOpt = Annotated[Path | None, typer.Option("--out", help="File to write.")]
_DEFAULT_DIR = Path("minitest-script-runs")


def _saved(path: Path, json_mode: bool, **extra: str) -> None:
    if json_mode:
        print_json({"path": str(path), **extra})
    else:
        print_success(f"Saved {path}")


def _download_artifact(
    run_id: str, test: str | None, out: Path | None, *, kind: str, kept: str, suffix: str
) -> None:
    settings, app_id, json_mode = resolve_app()
    ensure_uuid(run_id, kind="script run id")
    session = pick_test(run_api_call(fetch_run(settings, app_id, run_id)), test)
    url = session.video_url if kind == "recording" else session.log_url
    if url is None:
        print_error(_missing(session, kind, kept))
        raise typer.Exit(code=EXIT_NOT_FOUND)
    path = out or _DEFAULT_DIR / run_id / f"{session.scripted_run_id}{suffix}"
    run_api_call(download(url, path))
    _saved(path, json_mode, test=session.scripted_run_id)


def _missing(session: ScriptSession, kind: str, kept: str) -> str:
    if session.finished_at is None:
        return f"Test '{test_label(session)}' is still running: its {kind} comes when it ends."
    return (
        f"Test '{test_label(session)}' has no {kind}: none was uploaded, or it was deleted by the "
        f"retention policy ({kept})."
    )


def recording(run_id: RunArg, test: TestOpt = None, out: OutOpt = None) -> None:
    """Download a test's screen recording (MP4)."""
    _download_artifact(
        run_id, test, out, kind="recording", kept="recordings are kept 90 days", suffix=".mp4"
    )


def appium_log(run_id: RunArg, test: TestOpt = None, out: OutOpt = None) -> None:
    """Download a test's Appium server log."""
    _download_artifact(
        run_id, test, out, kind="Appium log", kept="Appium logs are kept 30 days", suffix=".log"
    )


def junit(run_id: RunArg, out: OutOpt = None) -> None:
    """Download the run as a JUnit XML report, one suite per test."""
    settings, app_id, json_mode = resolve_app()
    ensure_uuid(run_id, kind="script run id")

    async def _junit() -> bytes:
        async with ApiClient(settings) as client:
            resp = await client.get(
                f"{script_runs_path(app_id)}/{run_id}", params={"format": "junit"}
            )
        if resp.status_code == 404:
            print_error(f"Script run {run_id} not found for this app ({RUN_RETENTION}).")
            raise typer.Exit(code=EXIT_NOT_FOUND)
        handle_response_error(resp, resource="Script run")
        return resp.content

    path = out or _DEFAULT_DIR / run_id / "junit.xml"
    content = run_api_call(_junit())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    _saved(path, json_mode)


def register_artifact_commands(app: typer.Typer) -> None:
    app.command(name="recording")(recording)
    app.command(name="appium-log")(appium_log)
    app.command(name="junit")(junit)
