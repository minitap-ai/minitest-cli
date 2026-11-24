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
from minitest_cli.utils.output import print_error, print_warning

EXIT_NETWORK_ERROR = 3
EXIT_NOT_FOUND = 4


def account_credentials_path(app_id: str, account_id: str) -> str:
    """Where a test account's login and credentials are edited."""
    return f"/api/v1/apps/{app_id}/test-profiles/{account_id}"


def handle_api_response(resp: httpx.Response, *, resource: str) -> None:
    if resp.status_code == 404:
        detail = extract_detail(resp)
        print_error(detail or f"{resource} not found.")
        raise typer.Exit(code=EXIT_NOT_FOUND)
    if resp.status_code >= 400:
        detail = extract_detail(resp)
        print_error(detail or f"API error: {resp.status_code}")
        raise typer.Exit(code=EXIT_NETWORK_ERROR)


def read_stdin_secret(
    value: str | None, use_stdin: bool, *, value_flag: str, stdin_flag: str
) -> str | None:
    if use_stdin:
        if value is not None:
            print_error(f"Use either {value_flag} or {stdin_flag}, not both.")
            raise typer.Exit(code=1)
        return sys.stdin.read().rstrip("\r\n")
    return value


def warn_if_qa_inbox_unreadable(account: dict[str, Any]) -> None:
    if account.get("qaInboxShared"):
        print_warning(
            f"{account.get('username')} belongs to another workspace, so Mini can't read its "
            "emails (login codes, verification links). Use a different @qa.minitap.ai address."
        )


__all__ = [
    "EXIT_NETWORK_ERROR",
    "EXIT_NOT_FOUND",
    "account_credentials_path",
    "get_app_flag",
    "get_settings",
    "handle_api_response",
    "is_json_mode",
    "read_stdin_secret",
    "run_api_call",
    "warn_if_qa_inbox_unreadable",
]
