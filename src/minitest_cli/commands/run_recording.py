"""`minitest run recording` and `minitest run frames`: look at what a run actually did."""

import json
from pathlib import Path
from typing import Annotated

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.recording_timeline import build_timeline, recording_source
from minitest_cli.commands.run_helpers import (
    EXIT_NOT_FOUND,
    base_path,
    ensure_uuid,
    handle_response_error,
    resolve_app,
    run_api_call,
)
from minitest_cli.commands.run_recording_helpers import (
    attach_criterion_frames,
    default_out_dir,
    download,
    select_platform_run,
)
from minitest_cli.models.story_run import StoryRunResponse
from minitest_cli.utils.output import print_error, print_json, print_table, print_warning
from minitest_cli.utils.video_frames import (
    FrameExtractionError,
    build_strips,
    clamp_times,
    probe_duration,
    require_ffmpeg,
    stepped_times,
)

WidthOpt = Annotated[int, typer.Option("--width", min=32, help="Frame width in pixels.")]


def recording(
    run_id: Annotated[str, typer.Argument(help="Story-run ID.")],
    platform: Annotated[str | None, typer.Option(help="Target platform (ios/android/web).")] = None,
    srp: Annotated[str | None, typer.Option(help="Exact target (srpId) when ambiguous.")] = None,
    device: Annotated[int, typer.Option(min=1, help="Device index on multi-device runs.")] = 1,
    out: Annotated[Path | None, typer.Option(help="Output directory.")] = None,
    criterion_frames: Annotated[
        int,
        typer.Option(
            min=0,
            help="Frames per criterion strip, spread over its observation window. 0 to skip.",
        ),
    ] = 4,
    width: WidthOpt = 240,
) -> None:
    """Download a run's reduced recording with every criterion verdict and agent action timed on it.

    Writes recording.mp4, timeline.json and criteria/NN-<status>.png strips.
    """
    settings, app_id, json_mode = resolve_app()
    ensure_uuid(run_id, kind="run id")

    async def _fetch() -> StoryRunResponse:
        async with ApiClient(settings) as client:
            resp = await client.get(f"{base_path(app_id)}/{run_id}")
            handle_response_error(resp, resource="Run")
            return StoryRunResponse.model_validate(resp.json())

    run = run_api_call(_fetch())
    platform_run = select_platform_run(run, platform, srp)
    source = recording_source(platform_run, device)
    if source is None:
        print_error(f"No recording for device {device} on {platform_run.platform} yet.")
        raise typer.Exit(code=EXIT_NOT_FOUND)

    out_dir = out or default_out_dir(run.id, platform_run, device)
    video = out_dir / "recording.mp4"
    run_api_call(download(source.url, video))

    timeline = build_timeline(
        run,
        platform_run,
        device_index=device,
        source=source,
        video_path=str(video),
        duration_sec=probe_duration(video),
    )
    if criterion_frames:
        try:
            require_ffmpeg()
            attach_criterion_frames(
                timeline, video, out_dir, per_criterion=criterion_frames, width=width
            )
        except FrameExtractionError as exc:
            print_warning(f"{exc} Skipping criterion frames.")

    payload = timeline.model_dump(mode="json", by_alias=True, exclude_none=True)
    (out_dir / "timeline.json").write_text(json.dumps(payload, indent=2))
    if json_mode:
        print_json(payload)
        return
    rows = [
        [
            c.status or "-",
            "-"
            if c.observed_from_sec is None
            else f"{c.observed_from_sec}–{c.observed_until_sec}s",
            (c.content or "")[:70],
            c.frames_path or "-",
        ]
        for c in timeline.criteria
    ]
    print_table(["Status", "Video time", "Criterion", "Frames"], rows, title=str(out_dir))


def frames(
    video: Annotated[Path, typer.Argument(exists=True, dir_okay=False, help="Local video file.")],
    start: Annotated[float, typer.Option(min=0, help="First timestamp, in seconds.")] = 0.0,
    end: Annotated[float | None, typer.Option(help="Last timestamp (default: video end).")] = None,
    every: Annotated[float, typer.Option(min=0.1, help="Seconds between frames.")] = 2.0,
    at: Annotated[
        list[float] | None, typer.Option("--at", help="Exact timestamps; overrides the range.")
    ] = None,
    columns: Annotated[int, typer.Option(min=1, help="Frames per strip image.")] = 10,
    width: WidthOpt = 200,
    out: Annotated[Path, typer.Option(help="Output directory.")] = Path("frames"),
) -> None:
    """Sample frames from a video into left-to-right strip images."""
    duration = probe_duration(video)
    last = end if end is not None else duration
    if not at and last is None:
        print_error("Cannot read the video duration; pass --end or --at.")
        raise typer.Exit(code=1)
    times = clamp_times(at or stepped_times(start, last or start, every), duration)
    try:
        require_ffmpeg()
        strips = build_strips(video, times, out, width=width, columns=columns)
    except FrameExtractionError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc
    print_json([{"path": str(path), "timesSec": chunk} for path, chunk in strips])


def register_recording_commands(app: typer.Typer) -> None:
    app.command(name="recording")(recording)
    app.command(name="frames")(frames)
