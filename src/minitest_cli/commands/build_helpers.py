"""Helpers for build commands: shared constants, API utilities, formatting."""

import asyncio
import math
from collections.abc import Coroutine
from enum import StrEnum
from pathlib import Path

import httpx
import typer

from minitest_cli.core.app_context import resolve_app_id
from minitest_cli.core.config import Settings
from minitest_cli.models import BuildListResponse, BuildResponse
from minitest_cli.utils.output import print_error

EXIT_NETWORK_ERROR = 3
EXIT_NOT_FOUND = 4

# ---------------------------------------------------------------------------
# Context accessors
# ---------------------------------------------------------------------------


def get_settings() -> Settings:
    return typer.Context.settings  # type: ignore[attr-defined]


def is_json_mode() -> bool:
    return typer.Context.json_mode  # type: ignore[attr-defined]


def get_app_flag() -> str | None:
    return typer.Context.app_flag  # type: ignore[attr-defined]


def resolve_app() -> tuple[Settings, str, bool]:
    """Return (settings, app_id, json_mode) — exits on auth/app failure."""
    from minitest_cli.core.auth import require_auth

    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)
    app_id = resolve_app_id(settings, get_app_flag())
    return settings, app_id, json_mode


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------


class Platform(StrEnum):
    ios = "ios"
    android = "android"


PLATFORM_EXTENSIONS: dict[str, Platform] = {
    ".ipa": Platform.ios,
    ".apk": Platform.android,
}


def detect_platform(file_path: Path) -> str:
    """Auto-detect platform from file extension."""
    suffix = file_path.suffix.lower()
    platform = PLATFORM_EXTENSIONS.get(suffix)
    if platform is None:
        print_error(
            f"Cannot detect platform from extension '{suffix}'. "
            "Use --platform to specify ios or android."
        )
        raise typer.Exit(code=1)
    return platform


# ---------------------------------------------------------------------------
# API error handling
# ---------------------------------------------------------------------------


def extract_detail(resp: httpx.Response) -> str:
    """Extract a human-readable error detail from an API response."""
    try:
        body = resp.json()
        return str(body.get("detail", body.get("message", resp.text)))
    except Exception:  # noqa: BLE001
        return resp.text


def handle_response_error(resp: httpx.Response, *, resource: str = "Build") -> None:
    """Check response status; exit with proper code on errors."""
    if resp.status_code == 404:
        print_error(f"{resource} not found: {extract_detail(resp)}")
        raise typer.Exit(code=EXIT_NOT_FOUND)
    if resp.status_code >= 400:
        print_error(f"API error ({resp.status_code}): {extract_detail(resp)}")
        raise typer.Exit(code=EXIT_NETWORK_ERROR)


def run_api_call[T](coro: Coroutine[object, object, T]) -> T:
    """Run an async API coroutine, catching network errors → exit 3."""
    try:
        return asyncio.run(coro)
    except httpx.HTTPError as exc:
        print_error(f"Network error: {exc}")
        raise typer.Exit(code=EXIT_NETWORK_ERROR) from None


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

BUILD_TABLE_HEADERS = ["ID", "Platform", "Filename", "Size", "Created"]


def format_file_size(size_bytes: int | float | None) -> str:
    """Format bytes into a human-readable string."""
    if size_bytes is None:
        return "—"
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def format_build_row(build: BuildResponse) -> list[str]:
    """Format a single BuildResponse as a table row."""
    return [
        build.id,
        build.platform,
        build.original_name,
        format_file_size(build.size_bytes),
        build.created_at.strftime("%Y-%m-%d %H:%M"),
    ]


def format_pagination_info(data: BuildListResponse) -> tuple[str, str]:
    """Return (title, tip) for paginated table display."""
    total_pages = math.ceil(data.total / data.page_size)
    start = (data.page - 1) * data.page_size + 1
    end = min(data.page * data.page_size, data.total)
    title = f"Builds — page {data.page} of {total_pages}, showing {start}–{end} of {data.total}"

    tip = ""
    if data.page < total_pages:
        tip = f"Use --page {data.page + 1} to see next page, or --all to fetch everything."
    return title, tip


def upload_status_message(file_path: Path) -> str:
    """Build the upload status message."""
    file_size = file_path.stat().st_size
    return f"[bold blue]Uploading {file_path.name} ({format_file_size(file_size)})…"


def base_path(app_id: str) -> str:
    """Return the base API path for builds."""
    return f"/api/v1/apps/{app_id}"
