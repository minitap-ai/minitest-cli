"""Helpers for the per-story camera-media flag (upload or reuse a test file)."""

import mimetypes
import uuid
from pathlib import Path
from typing import Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.test_file_helpers import base_path as test_files_base_path
from minitest_cli.commands.test_file_helpers import handle_file_response
from minitest_cli.utils.output import print_error, print_info

CAMERA_IMAGE_MAX_BYTES = 25 * 1024 * 1024
CAMERA_VIDEO_MAX_BYTES = 50 * 1024 * 1024

CAMERA_MEDIA_HELP = (
    "Camera media fed to the virtual webcam during web runs: a local video/image "
    "path to upload (video ≤ 50 MB, image ≤ 25 MB) or an existing test-file ID."
)


def resolve_camera_source(camera_media: str | None) -> str | Path | None:
    """Parse the ``--camera-media`` value, or ``None`` when the flag was omitted."""
    return parse_camera_media(camera_media) if camera_media is not None else None


async def resolve_camera_media_file_id(
    client: ApiClient, app_id: str, camera_source: str | Path
) -> str:
    """Return the test-file ID for a camera source, uploading a path if needed."""
    if isinstance(camera_source, Path):
        return await upload_camera_media(client, app_id, camera_source)
    return camera_source


def parse_camera_media(value: str) -> str | Path:
    """Return an existing test-file ID, or a validated local path to upload.

    UUID-shaped values are treated as test-file IDs. Anything else must be an
    existing local video/image file within the per-kind size cap.
    """
    try:
        uuid.UUID(value)
    except ValueError:
        pass
    else:
        return value

    path = Path(value).expanduser()
    if not path.is_file():
        print_error(f"--camera-media must be an existing file or a test-file ID: {value}")
        raise typer.Exit(code=1)

    mime, _ = mimetypes.guess_type(path.name)
    if not mime or not mime.startswith(("image/", "video/")):
        print_error("Camera media must be a video or image file.")
        raise typer.Exit(code=1)

    limit = CAMERA_VIDEO_MAX_BYTES if mime.startswith("video/") else CAMERA_IMAGE_MAX_BYTES
    size = path.stat().st_size
    if size > limit:
        limit_mb = limit // (1024 * 1024)
        kind = "video" if mime.startswith("video/") else "image"
        print_error(f"Camera media too large: {size} bytes (max {limit_mb} MB for {kind}).")
        raise typer.Exit(code=1)
    return path


async def upload_camera_media(client: ApiClient, app_id: str, path: Path) -> str:
    """Upload the camera-media file as a test file and return its ID."""
    mime, _ = mimetypes.guess_type(path.name)
    mime = mime or "application/octet-stream"
    with path.open("rb") as fh:
        resp = await client.upload_file(
            test_files_base_path(app_id),
            files={"file": (path.name, fh, mime)},
        )
    handle_file_response(resp)
    body: dict[str, Any] = resp.json()
    file_id = body.get("id")
    if not file_id:
        print_error("Server did not return an id for the uploaded camera media.")
        raise typer.Exit(code=1)
    print_info(f"Camera media uploaded as test file: {file_id}")
    return str(file_id)
