"""`minitest run frames` against a real video rendered by ffmpeg."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from minitest_cli.commands.run import app as run_app

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not installed",
)

runner = CliRunner()


def _size(image: Path) -> tuple[int, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0", image],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    width, height = out.split(",")
    return int(width), int(height)


@pytest.fixture
def video(tmp_path: Path) -> Path:
    path = tmp_path / "clip.mp4"
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x640:rate=10",
         "-t", "5", "-pix_fmt", "yuv420p", path],
        check=True,
    )  # fmt: skip
    return path


class TestRunFrames:
    def test_frames_splits_samples_into_strips_of_columns(self, video: Path, tmp_path: Path):
        out = tmp_path / "frames"

        result = runner.invoke(
            run_app,
            ["frames", str(video), "--every", "1", "--columns", "4", "--width", "100",
             "--out", str(out)],
        )  # fmt: skip

        assert result.exit_code == 0, result.output
        strips = json.loads(result.stdout)
        # The 5s mark is past the last frame, so it is pulled back onto it.
        assert [s["timesSec"] for s in strips] == [[0.0, 1.0, 2.0, 3.0], [4.0, 4.5]]
        assert _size(Path(strips[0]["path"])) == (400, 200)
        assert _size(Path(strips[1]["path"])) == (200, 200)

    def test_frames_at_exact_timestamps(self, video: Path, tmp_path: Path):
        result = runner.invoke(
            run_app,
            ["frames", str(video), "--at", "2.5", "--width", "80", "--out", str(tmp_path / "f")],
        )

        assert result.exit_code == 0, result.output
        [strip] = json.loads(result.stdout)
        assert strip["timesSec"] == [2.5]
        assert _size(Path(strip["path"])) == (80, 160)
