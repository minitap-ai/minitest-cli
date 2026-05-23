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

EXIT_NETWORK_ERROR = 3
EXIT_NOT_FOUND = 4

PROFILE_TABLE_HEADERS = ["ID", "Name", "Username", "Scope", "Updated At"]


def app_base_path(app_id: str) -> str:
    return f"/api/v1/apps/{app_id}/test-profiles"


SHARED_PATH = "/api/v1/test-profiles/shared"


def handle_profile_response(resp: httpx.Response, *, resource: str = "Test profile") -> None:
    if resp.status_code == 404:
        detail = extract_detail(resp)
        print_error(detail or f"{resource} not found.")
        raise typer.Exit(code=EXIT_NOT_FOUND)
    if resp.status_code >= 400:
        detail = extract_detail(resp)
        print_error(detail or f"API error: {resp.status_code}")
        raise typer.Exit(code=EXIT_NETWORK_ERROR)


def profile_scope(profile: dict[str, Any]) -> str:
    if profile.get("isShared") or profile.get("is_shared"):
        return "shared"
    return "app"


def format_profile_row(profile: dict[str, Any]) -> list[str]:
    return [
        str(profile.get("id", "")),
        profile.get("name", ""),
        profile.get("username") or "",
        profile_scope(profile),
        profile.get("updatedAt") or profile.get("updated_at") or "",
    ]


__all__ = [
    "EXIT_NETWORK_ERROR",
    "EXIT_NOT_FOUND",
    "PROFILE_TABLE_HEADERS",
    "SHARED_PATH",
    "app_base_path",
    "extract_detail",
    "format_profile_row",
    "get_app_flag",
    "get_settings",
    "handle_profile_response",
    "is_json_mode",
    "run_api_call",
]
