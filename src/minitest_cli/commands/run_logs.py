"""`minitest run logs`: download the log files a scenario run's target captured."""

import gzip
import shutil
from pathlib import Path
from typing import Annotated

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.run_helpers import (
    EXIT_NOT_FOUND,
    base_path,
    ensure_uuid,
    handle_response_error,
    resolve_app,
    run_api_call,
)
from minitest_cli.commands.run_recording_helpers import download, select_platform_run
from minitest_cli.models.lane_logs import LaneLogFile, LaneLogs
from minitest_cli.models.story_run import PlatformRun, StoryRunResponse
from minitest_cli.utils.output import print_error, print_info, print_json, print_table

_FILE_LABELS = {
    "device_log": "Device log",
    "crash_report": "Crash report",
    "browser_console": "Browser console",
    "network_har": "Network (HAR)",
}


def logs(
    run_id: Annotated[str, typer.Argument(help="Scenario-run ID.")],
    platform: Annotated[str | None, typer.Option(help="Target platform (ios/android/web).")] = None,
    target_id: Annotated[
        str | None, typer.Option("--target-id", help="Exact target (srpId) when ambiguous.")
    ] = None,
    out: Annotated[Path | None, typer.Option(help="Output directory.")] = None,
) -> None:
    """Download a run's log files: device log, crash report, browser console, network (HAR).

    Files are written decompressed. Crashes found in the device log are listed with
    their time on the recording.
    """
    settings, app_id, json_mode = resolve_app()
    ensure_uuid(run_id, kind="run id")

    async def _fetch() -> tuple[PlatformRun, LaneLogs]:
        async with ApiClient(settings) as client:
            resp = await client.get(f"{base_path(app_id)}/{run_id}")
            handle_response_error(resp, resource="Run")
            target = select_platform_run(
                StoryRunResponse.model_validate(resp.json()), platform, target_id
            )
            resp = await client.get(
                f"{base_path(app_id)}/{run_id}/lane-logs", params={"srp_id": target.srp_id}
            )
            if resp.status_code == 404:
                print_error("No logs for this run: logs aren't enabled for your workspace.")
                raise typer.Exit(code=EXIT_NOT_FOUND)
            handle_response_error(resp, resource="Run")
            return target, LaneLogs.model_validate(resp.json())

    target, lane_logs = run_api_call(_fetch())
    _exit_without_files(lane_logs, target)
    out_dir = out or Path("minitest-logs") / f"{run_id}-{target.platform}"
    written = [(file, run_api_call(_save(file, out_dir))) for file in lane_logs.files]

    if json_mode:
        print_json(
            {
                "files": [
                    {"kind": f.kind, "path": str(path), "bytes": path.stat().st_size}
                    for f, path in written
                ],
                "crashes": [c.model_dump(by_alias=True) for c in lane_logs.crashes],
            }
        )
        return
    rows = [[_FILE_LABELS.get(f.kind, f.kind), _size(path), str(path)] for f, path in written]
    print_table(["File", "Size", "Path"], rows, title=str(out_dir))
    for crash in lane_logs.crashes:
        print_info(f"App crash {_clock(crash.offset_ms)} into the run: {crash.summary}")


def _exit_without_files(lane_logs: LaneLogs, target: PlatformRun) -> None:
    if lane_logs.files:
        return
    if lane_logs.status == "pending":
        print_error(f"The {target.platform} target is still running; logs arrive when it ends.")
        raise typer.Exit(code=1)
    print_error(
        f"No logs were captured for the {target.platform} target "
        "(physical iPhones aren't captured yet)."
    )
    raise typer.Exit(code=EXIT_NOT_FOUND)


async def _save(file: LaneLogFile, out_dir: Path) -> Path:
    dest = out_dir / file.file_name
    if not file.compressed:
        await download(file.url, dest)
        return dest
    packed = dest.with_name(f"{dest.name}.gz")
    await download(file.url, packed)
    with gzip.open(packed, "rb") as source, dest.open("wb") as target:
        shutil.copyfileobj(source, target)
    packed.unlink()
    return dest


def _size(path: Path) -> str:
    size = path.stat().st_size
    return f"{size / 1024**2:.1f} MB" if size >= 1024**2 else f"{size / 1024:.0f} KB"


def _clock(offset_ms: int) -> str:
    minutes, seconds = divmod(offset_ms / 1000, 60)
    return f"{int(minutes)}:{seconds:04.1f}"


def register_logs_command(app: typer.Typer) -> None:
    app.command(name="logs")(logs)
