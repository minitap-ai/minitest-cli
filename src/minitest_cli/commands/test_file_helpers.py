from __future__ import annotations

from typing import Any

import httpx
import typer

from minitest_cli.commands.user_story_helpers import (
    extract_detail,
    get_app_flag,
    get_settings,
    is_json_mode,
    run_api_call,
)
from minitest_cli.utils.output import print_error

EXIT_GENERAL_ERROR = 1
EXIT_NETWORK_ERROR = 3
EXIT_NOT_FOUND = 4

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # mirrors the testing-service multipart cap

FILE_TABLE_HEADERS = ["ID", "Name", "Original Filename", "Kind", "MIME", "Size", "Updated At"]


def base_path(app_id: str) -> str:
    return f"/api/v1/apps/{app_id}/test-files"


def handle_file_response(resp: httpx.Response, *, resource: str = "Test file") -> None:
    if resp.status_code == 404:
        detail = extract_detail(resp)
        print_error(detail or f"{resource} not found.")
        raise typer.Exit(code=EXIT_NOT_FOUND)
    if resp.status_code >= 400:
        detail = extract_detail(resp)
        print_error(detail or f"API error: {resp.status_code}")
        raise typer.Exit(code=EXIT_NETWORK_ERROR)


def format_file_row(entry: dict[str, Any]) -> list[str]:
    size = entry.get("sizeBytes") or entry.get("size_bytes") or 0
    return [
        str(entry.get("id", "")),
        entry.get("name", ""),
        entry.get("originalFilename") or entry.get("original_filename") or "",
        entry.get("kind", "") or "",
        entry.get("mimeType") or entry.get("mime_type") or "",
        str(size),
        entry.get("updatedAt") or entry.get("updated_at") or "",
    ]


__all__ = [
    "EXIT_GENERAL_ERROR",
    "EXIT_NETWORK_ERROR",
    "EXIT_NOT_FOUND",
    "FILE_TABLE_HEADERS",
    "MAX_UPLOAD_BYTES",
    "base_path",
    "extract_detail",
    "format_file_row",
    "get_app_flag",
    "get_settings",
    "handle_file_response",
    "is_json_mode",
    "run_api_call",
]
