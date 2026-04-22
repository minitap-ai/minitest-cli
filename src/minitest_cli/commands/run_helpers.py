"""Helpers for run commands: resolution, polling, API utilities."""

import asyncio
import re
from collections.abc import Coroutine
from typing import Any

import httpx
import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.core.app_context import resolve_app_id
from minitest_cli.core.config import Settings
from minitest_cli.models.story_run import RunStatus, StoryRunListResponse, StoryRunResponse
from minitest_cli.utils.output import err_console, print_error

from minitest_cli.commands.run_display import (  # noqa: F401
    RESULTS_TABLE_HEADERS,
    RUN_TABLE_HEADERS,
    display_run_result,
    format_run_pagination_info,
    format_run_row,
)

EXIT_NETWORK_ERROR = 3
EXIT_NOT_FOUND = 4

UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

POLL_INTERVAL_SECONDS = 2

TERMINAL_STATUSES = {RunStatus.completed, RunStatus.failed}


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


def base_path(app_id: str) -> str:
    """Return the base API path for story runs."""
    return f"/api/v1/apps/{app_id}/story-runs"


def extract_detail(resp: httpx.Response) -> str | None:
    """Extract a human-readable error detail from an API response."""
    try:
        body = resp.json()
        if isinstance(body, dict):
            return body.get("detail") or body.get("message")
    except Exception:  # noqa: BLE001
        pass
    return None


def handle_response_error(resp: httpx.Response, *, resource: str = "Run") -> None:
    """Check response status; exit with proper code on errors."""
    if resp.status_code == 404:
        detail = extract_detail(resp)
        print_error(detail or f"{resource} not found.")
        raise typer.Exit(code=EXIT_NOT_FOUND)
    if resp.status_code == 500:
        detail = extract_detail(resp) or ""
        if "violates foreign key constraint" in detail:
            msg = f"{resource} references a resource that does not exist."
            print_error(f"{msg} Check the user-story and build IDs.")
            raise typer.Exit(code=EXIT_NOT_FOUND)
    if resp.status_code >= 400:
        detail = extract_detail(resp)
        print_error(detail or f"API error: {resp.status_code}")
        raise typer.Exit(code=EXIT_NETWORK_ERROR)


def run_api_call[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run an async API coroutine, catching network errors → exit 3."""
    try:
        return asyncio.run(coro)
    except httpx.HTTPError as exc:
        print_error(f"Network error: {exc}")
        raise typer.Exit(code=EXIT_NETWORK_ERROR) from exc


def is_uuid(value: str) -> bool:
    """Check if a string looks like a UUID."""
    return bool(UUID_PATTERN.match(value))


async def resolve_user_story_id(
    client: ApiClient,
    app_id: str,
    user_story_ref: str,
) -> str:
    """Resolve a user-story name or UUID to a user-story ID.

    If user_story_ref is a UUID, returns it directly.
    Otherwise fetches the user-story list and does case-insensitive name match.
    """
    if is_uuid(user_story_ref):
        return user_story_ref

    resp = await client.get(
        f"/api/v1/apps/{app_id}/user-stories",
        params={"page_size": 100},
    )
    handle_response_error(resp, resource="User story")

    items = resp.json().get("items", [])
    for story in items:
        if story.get("name", "").lower() == user_story_ref.lower():
            return story["id"]

    print_error(f"User story not found: '{user_story_ref}'. Use a valid user-story name or UUID.")
    raise typer.Exit(code=EXIT_NOT_FOUND)


async def fetch_runs(
    client: ApiClient,
    app_id: str,
    user_story_id: str,
    page: int,
    page_size: int,
    status_filter: str | None,
) -> StoryRunListResponse:
    """Fetch paginated runs for a user story."""
    params: dict[str, str | int] = {"page": page, "page_size": page_size}
    if status_filter is not None:
        params["status"] = status_filter

    resp = await client.get(
        f"/api/v1/apps/{app_id}/user-stories/{user_story_id}/story-runs",
        params=params,
    )
    handle_response_error(resp, resource="Runs")
    return StoryRunListResponse.model_validate(resp.json())


async def poll_run_status(
    client: ApiClient,
    app_id: str,
    run_id: str,
    json_mode: bool,
) -> StoryRunResponse:
    """Poll a run until it reaches a terminal status. Returns final state."""
    path = f"{base_path(app_id)}/{run_id}"

    with err_console.status("[bold blue]Waiting for run to complete…") as spinner:
        while True:
            resp = await client.get(path)
            handle_response_error(resp, resource="Run")

            run = StoryRunResponse.model_validate(resp.json())

            spinner.update(f"[bold blue]Running… status: {run.status.value}")

            if run.status in TERMINAL_STATUSES:
                return run

            await asyncio.sleep(POLL_INTERVAL_SECONDS)
