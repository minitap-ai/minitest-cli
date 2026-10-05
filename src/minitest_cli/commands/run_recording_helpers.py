"""Target selection, download and per-criterion frames for `run recording`."""

from pathlib import Path

import httpx
import typer

from minitest_cli.api.client import UPLOAD_TIMEOUT
from minitest_cli.commands.run_helpers import EXIT_NOT_FOUND
from minitest_cli.models.recording import RecordingTimeline
from minitest_cli.models.story_run import PlatformRun, StoryRunResponse
from minitest_cli.utils.output import print_error
from minitest_cli.utils.video_frames import build_strip, clamp_times, spread_times

CRITERION_PAD_SEC = 1.0


def select_platform_run(
    run: StoryRunResponse, platform: str | None, srp_id: str | None
) -> PlatformRun:
    candidates = [
        p
        for p in run.platforms
        if (platform is None or p.platform == platform) and (srp_id is None or p.srp_id == srp_id)
    ]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        print_error("No target of this run matches the given --platform/--srp.")
        raise typer.Exit(code=EXIT_NOT_FOUND)
    with_recording = [p for p in candidates if p.recording_url or p.device_recordings]
    if len(with_recording) == 1:
        return with_recording[0]
    listing = ", ".join(f"{p.platform} (srp {p.srp_id})" for p in candidates)
    print_error(f"This run has several targets: {listing}. Pick one with --platform or --srp.")
    raise typer.Exit(code=1)


def default_out_dir(run_id: str, platform_run: PlatformRun, device_index: int) -> Path:
    suffix = f"-device{device_index}" if device_index != 1 else ""
    return Path("minitest-recordings") / f"{run_id}-{platform_run.platform}{suffix}"


async def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".part")
    # Signed storage URL: it must not carry the Minitest bearer token.
    async with (
        httpx.AsyncClient(timeout=UPLOAD_TIMEOUT, follow_redirects=True) as client,
        client.stream("GET", url) as resp,
    ):
        resp.raise_for_status()
        with partial.open("wb") as fh:
            async for chunk in resp.aiter_bytes():
                fh.write(chunk)
    partial.replace(dest)


def attach_criterion_frames(
    timeline: RecordingTimeline, video: Path, out_dir: Path, *, per_criterion: int, width: int
) -> None:
    for n, criterion in enumerate(timeline.criteria, start=1):
        if criterion.observed_from_sec is None or criterion.observed_until_sec is None:
            continue
        times = clamp_times(
            spread_times(
                criterion.observed_from_sec - CRITERION_PAD_SEC,
                criterion.observed_until_sec + CRITERION_PAD_SEC,
                per_criterion,
            ),
            timeline.duration_sec,
        )
        out = out_dir / "criteria" / f"{n:02d}-{criterion.status or 'unknown'}.png"
        criterion.frames_path = str(build_strip(video, times, out, width=width))
