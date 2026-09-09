from __future__ import annotations

import sys
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

PROFILE_TABLE_HEADERS = ["ID", "Name", "Username", "Phone", "Scope", "Default", "Updated At"]


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


def is_default_profile(profile: dict[str, Any]) -> bool:
    return bool(profile.get("isDefault") or profile.get("is_default"))


def format_profile_row(profile: dict[str, Any]) -> list[str]:
    return [
        str(profile.get("id", "")),
        profile.get("name", ""),
        profile.get("username") or "",
        profile.get("phoneNumber") or profile.get("phone_number") or "",
        profile_scope(profile),
        "★" if is_default_profile(profile) else "",
        profile.get("updatedAt") or profile.get("updated_at") or "",
    ]


def read_stdin_secret(
    value: str | None, use_stdin: bool, *, value_flag: str, stdin_flag: str
) -> str | None:
    if use_stdin:
        if value is not None:
            print_error(f"Use either {value_flag} or {stdin_flag}, not both.")
            raise typer.Exit(code=1)
        return sys.stdin.read().rstrip("\r\n")
    return value


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
    "read_stdin_secret",
    "run_api_call",
]
