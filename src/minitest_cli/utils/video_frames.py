"""Frame strips from a local video via the ffmpeg binaries on PATH."""

import shutil
import subprocess
import tempfile
from pathlib import Path

# Seeking past the last decoded frame silently yields nothing; low-fps recordings need slack.
END_MARGIN_SEC = 0.5


class FrameExtractionError(RuntimeError):
    pass


class FfmpegMissingError(FrameExtractionError):
    pass


def require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise FfmpegMissingError(
            "ffmpeg is required to extract frames. Install it (e.g. `brew install ffmpeg`, "
            "`apt install ffmpeg`) or drop the frame options."
        )


def probe_duration(video: Path) -> float | None:
    if shutil.which("ffprobe") is None:
        return None
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        return round(float(proc.stdout.strip()), 3)
    except ValueError:
        return None


def stepped_times(start: float, end: float, every: float) -> list[float]:
    count = int((end - start) / every + 1e-9) + 1
    return [round(start + i * every, 3) for i in range(count)]


def spread_times(start: float, end: float, count: int) -> list[float]:
    if count <= 1 or end <= start:
        return [round(start, 3)]
    step = (end - start) / (count - 1)
    return [round(start + i * step, 3) for i in range(count)]


def clamp_times(times: list[float], duration: float | None) -> list[float]:
    upper = max(0.0, duration - END_MARGIN_SEC) if duration else None
    clamped = [max(0.0, t) if upper is None else min(max(0.0, t), upper) for t in times]
    return sorted(set(clamped))


def _ffmpeg(*args: str | Path) -> None:
    proc = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", *args], capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        raise FrameExtractionError(f"ffmpeg failed: {proc.stderr.strip()}")


def build_strip(video: Path, times: list[float], out: Path, *, width: int) -> Path:
    """One PNG with the frame at each timestamp side by side, left to right."""
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        frames = [Path(tmp) / f"f{i:03d}.png" for i in range(len(times))]
        for at, frame in zip(times, frames, strict=True):
            _ffmpeg(
                "-ss", f"{at}", "-i", video, "-frames:v", "1", "-vf", f"scale={width}:-2", frame
            )
            if not frame.exists():
                raise FrameExtractionError(f"No frame at {at}s in {video}.")
        if len(frames) == 1:
            shutil.copyfile(frames[0], out)
            return out
        inputs = [arg for frame in frames for arg in ("-i", frame)]
        _ffmpeg(*inputs, "-filter_complex", f"hstack=inputs={len(frames)}", out)
    return out


def build_strips(
    video: Path, times: list[float], out_dir: Path, *, width: int, columns: int
) -> list[tuple[Path, list[float]]]:
    chunks = [times[i : i + columns] for i in range(0, len(times), columns)]
    return [
        (build_strip(video, chunk, out_dir / f"strip-{n:02d}.png", width=width), chunk)
        for n, chunk in enumerate(chunks, start=1)
    ]
