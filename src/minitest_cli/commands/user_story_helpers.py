"""Shared helpers for user-story commands: API paths, response handling, formatting."""

import asyncio
from collections.abc import Coroutine
from typing import Any

import httpx
import typer

from minitest_cli.core.config import Settings
from minitest_cli.models.user_story import (
    UserStoryDetailResponse,
    UserStoryListResponse,
)
from minitest_cli.utils.output import print_error

EXIT_NETWORK_ERROR = 3
EXIT_NOT_FOUND = 4

USER_STORY_TABLE_HEADERS = ["ID", "Name", "Type", "Description", "Acceptance Criteria"]


def fetch_user_story_types(settings: Settings) -> list[str]:
    """Fetch valid user-story types from the API."""
    try:
        resp = httpx.get(
            f"{settings.api_url}/api/v1/user-story-types",
            timeout=10,
        )
    except httpx.HTTPError as exc:
        print_error(f"Failed to fetch user-story types: {exc}")
        raise typer.Exit(code=EXIT_NETWORK_ERROR) from exc
    if resp.status_code != 200:
        print_error(f"Failed to fetch user-story types: HTTP {resp.status_code}")
        raise typer.Exit(code=EXIT_NETWORK_ERROR)
    data = resp.json()
    if not isinstance(data, list) or not data:
        print_error("Invalid response from user-story types endpoint.")
        raise typer.Exit(code=EXIT_NETWORK_ERROR)
    return data


def validate_user_story_type(value: str, settings: Settings) -> str:
    """Validate a user-story type value against types from the API."""
    valid = fetch_user_story_types(settings)
    if value not in valid:
        print_error(f"Invalid user-story type '{value}'. Valid types: {', '.join(valid)}")
        raise typer.Exit(code=1)
    return value


def get_settings() -> Settings:
    return typer.Context.settings  # type: ignore[attr-defined]


def is_json_mode() -> bool:
    return typer.Context.json_mode  # type: ignore[attr-defined]


def get_app_flag() -> str | None:
    return typer.Context.app_flag  # type: ignore[attr-defined]


def base_path(app_id: str) -> str:
    return f"/api/v1/apps/{app_id}/user-stories"


def extract_detail(resp: httpx.Response) -> str | None:
    try:
        body = resp.json()
        if isinstance(body, dict):
            return body.get("detail") or body.get("message")
    except Exception:  # noqa: BLE001
        pass
    return None


def handle_response_error(resp: httpx.Response, *, resource: str = "User story") -> None:
    if resp.status_code == 404:
        detail = extract_detail(resp)
        print_error(detail or f"{resource} not found.")
        raise typer.Exit(code=EXIT_NOT_FOUND)
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


def format_user_story_row(story: dict[str, Any]) -> list[str]:
    criteria_str = ""
    try:
        parsed = UserStoryDetailResponse.model_validate(story)
        criteria_str = "; ".join(c.content for c in parsed.acceptance_criteria)
    except Exception:  # noqa: BLE001
        pass
    return [
        str(story.get("id", "")),
        story.get("name", ""),
        story.get("type", ""),
        story.get("description", "") or "",
        criteria_str,
    ]


def extract_criteria_strings(story_data: dict[str, Any]) -> list[str]:
    """Extract plain-text criteria from a user-story response, handling all formats."""
    raw = story_data.get("acceptanceCriteria") or story_data.get("acceptance_criteria") or []
    return [
        item.get("content", "") if isinstance(item, dict) else str(item)
        for item in raw
        if (item.get("content") if isinstance(item, dict) else item)
    ]


def extract_criteria_items(story_data: dict[str, Any]) -> list[dict[str, str]]:
    """Extract existing criteria as upsert items ``{id, content}``.

    The ``id`` uses the stable criterion identifier (``criterionId`` in the API
    response) so the backend preserves identity across updates.
    """
    raw = story_data.get("acceptanceCriteria") or story_data.get("acceptance_criteria") or []
    items: list[dict[str, str]] = []
    for entry in raw:
        if isinstance(entry, dict):
            content = entry.get("content")
            if not content:
                continue
            stable_id = entry.get("criterionId") or entry.get("criterion_id")
            item: dict[str, str] = {"content": content}
            if stable_id:
                item["id"] = stable_id
            items.append(item)
        elif entry:
            items.append({"content": str(entry)})
    return items


def format_pagination_info(
    data: dict[str, Any],
    page: int,
    page_size: int,
) -> tuple[str, str | None]:
    try:
        parsed = UserStoryListResponse.model_validate(data)
        total, current_page, current_page_size = parsed.total, parsed.page, parsed.page_size
        item_count = len(parsed.items)
    except Exception:  # noqa: BLE001
        total = data.get("total", 0) if isinstance(data, dict) else 0
        current_page = data.get("page", page) if isinstance(data, dict) else page
        current_page_size = data.get("pageSize", page_size) if isinstance(data, dict) else page_size
        items = data.get("items", []) if isinstance(data, dict) else []
        item_count = len(items)

    total_pages = (
        max(1, (total + current_page_size - 1) // current_page_size) if current_page_size > 0 else 1
    )
    if not item_count:
        start = end = 0
    else:
        start = (current_page - 1) * current_page_size + 1
        end = min(start + item_count - 1, total)

    title = f"User stories (Page {current_page} of {total_pages}, showing {start}-{end} of {total})"

    tip = None
    if current_page < total_pages:
        next_page = current_page + 1
        tip = (
            f"\n💡 Tip: Use --page {next_page} to see more, "
            f"or --all to fetch all {total} user stories"
        )
    elif total > current_page_size and current_page_size < 100:
        tip = f"\n💡 Tip: Use --all to fetch all {total} user stories in one request"

    return title, tip
