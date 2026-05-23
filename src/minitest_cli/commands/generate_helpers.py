"""Shared helpers for generation-job commands."""

import asyncio
from collections.abc import Coroutine
from typing import Any

import httpx
import typer

from minitest_cli.core.config import Settings
from minitest_cli.utils.output import print_error

EXIT_NETWORK_ERROR = 3
EXIT_NOT_FOUND = 4


def get_settings() -> Settings:
    return typer.Context.settings  # type: ignore[attr-defined]


def is_json_mode() -> bool:
    return typer.Context.json_mode  # type: ignore[attr-defined]


def get_app_flag() -> str | None:
    return typer.Context.app_flag  # type: ignore[attr-defined]


def base_path(app_id: str) -> str:
    return f"/api/v1/apps/{app_id}/generation-jobs"


def extract_detail(resp: httpx.Response) -> str | None:
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        return None
    if isinstance(body, dict):
        detail = body.get("detail")
        if isinstance(detail, str):
            return detail
        return body.get("message")
    return None


def handle_response_error(resp: httpx.Response, *, resource: str = "Generation job") -> None:
    if resp.status_code == 404:
        detail = extract_detail(resp)
        print_error(detail or f"{resource} not found.")
        raise typer.Exit(code=EXIT_NOT_FOUND)
    if resp.status_code == 403:
        detail = extract_detail(resp)
        print_error(detail or "Story generation is not enabled for this account.")
        raise typer.Exit(code=1)
    if resp.status_code == 409:
        detail = extract_detail(resp)
        print_error(detail or "A generation job is already running for this app.")
        raise typer.Exit(code=1)
    if resp.status_code >= 400:
        detail = extract_detail(resp)
        print_error(detail or f"API error: {resp.status_code}")
        raise typer.Exit(code=EXIT_NETWORK_ERROR)


def run_api_call[T](coro: Coroutine[Any, Any, T]) -> T:
    try:
        return asyncio.run(coro)
    except httpx.HTTPError as exc:
        print_error(f"Network error: {exc}")
        raise typer.Exit(code=EXIT_NETWORK_ERROR) from exc


JOB_TABLE_HEADERS = ["ID", "Status", "Repo", "Stories", "Created"]


def format_job_row(job: dict[str, Any]) -> list[str]:
    repo = f"{job.get('repoOwner', '')}/{job.get('repoName', '')}"
    return [
        str(job.get("id", "")),
        job.get("status", ""),
        repo,
        str(job.get("userStoriesCreated", 0)),
        str(job.get("createdAt", ""))[:16],
    ]
