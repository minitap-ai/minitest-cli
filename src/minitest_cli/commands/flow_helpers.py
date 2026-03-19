"""Shared helpers for flow commands: types, API paths, response handling, formatting."""

import asyncio
from collections.abc import Coroutine
from enum import StrEnum
from typing import Any

import httpx
import typer

from minitest_cli.core.config import Settings
from minitest_cli.utils.output import print_error

EXIT_NETWORK_ERROR = 3
EXIT_NOT_FOUND = 4

FLOW_TABLE_HEADERS = ["ID", "Name", "Type", "Description", "Acceptance Criteria"]


class FlowType(StrEnum):
    """Valid flow types for client-side validation."""

    login = "login"
    registration = "registration"
    checkout = "checkout"
    onboarding = "onboarding"
    search = "search"
    settings = "settings"
    navigation = "navigation"
    form = "form"
    profile = "profile"
    other = "other"


def get_settings() -> Settings:
    """Retrieve settings stored by the main callback."""
    return typer.Context.settings  # type: ignore[attr-defined]


def is_json_mode() -> bool:
    """Retrieve the global --json flag."""
    return typer.Context.json_mode  # type: ignore[attr-defined]


def get_app_flag() -> str | None:
    """Retrieve the global --app flag."""
    return typer.Context.app_flag  # type: ignore[attr-defined]


def base_path(app_id: str) -> str:
    """Build the base API path for flow-templates."""
    return f"/api/v1/apps/{app_id}/flow-templates"


def extract_detail(resp: httpx.Response) -> str | None:
    """Try to extract a detail message from a JSON error response."""
    try:
        body = resp.json()
        if isinstance(body, dict):
            return body.get("detail") or body.get("message")
    except Exception:  # noqa: BLE001
        pass
    return None


def handle_response_error(resp: httpx.Response, *, resource: str = "Flow") -> None:
    """Handle non-2xx responses with appropriate exit codes."""
    if resp.status_code == 404:
        detail = extract_detail(resp)
        print_error(detail or f"{resource} not found.")
        raise typer.Exit(code=EXIT_NOT_FOUND)
    if resp.status_code >= 400:
        detail = extract_detail(resp)
        print_error(detail or f"API error: {resp.status_code}")
        raise typer.Exit(code=EXIT_NETWORK_ERROR)


def run_api_call[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run an async API call, converting httpx errors to exit code 3."""
    try:
        return asyncio.run(coro)
    except httpx.HTTPError as exc:
        print_error(f"Network error: {exc}")
        raise typer.Exit(code=EXIT_NETWORK_ERROR) from exc


def format_flow_row(flow: dict[str, Any]) -> list[str]:
    """Format a flow dict as a table row."""
    raw_criteria = flow.get("acceptance_criteria")
    if raw_criteria is None:
        raw_criteria = flow.get("acceptanceCriteria") or []
    criteria = [
        item.get("content", "") if isinstance(item, dict) else str(item) for item in raw_criteria
    ]
    criteria_str = "; ".join(filter(None, criteria))
    return [
        str(flow.get("id", "")),
        flow.get("name", ""),
        flow.get("type", ""),
        flow.get("description", "") or "",
        criteria_str,
    ]


def format_pagination_info(
    data: dict[str, Any] | list[Any],
    page: int,
    page_size: int,
) -> tuple[str, str | None]:
    """Format pagination info for list output.

    Returns:
        (title, tip) where tip is None if no more pages
    """
    items = data if isinstance(data, list) else data.get("items", data.get("results", []))
    total = data.get("total", len(items)) if isinstance(data, dict) else len(items)
    current_page = data.get("page", page) if isinstance(data, dict) else page
    current_page_size = data.get("pageSize", page_size) if isinstance(data, dict) else page_size

    start = (current_page - 1) * current_page_size + 1
    end = min(start + len(items) - 1, total)
    total_pages = (
        (total + current_page_size - 1) // current_page_size if current_page_size > 0 else 1
    )

    title = f"Flows (Page {current_page} of {total_pages}, showing {start}-{end} of {total})"

    tip = None
    if current_page < total_pages:
        next_page = current_page + 1
        tip = f"\n💡 Tip: Use --page {next_page} to see more, or --all to fetch all {total} flows"
    elif total > current_page_size and current_page_size < 100:
        tip = f"\n💡 Tip: Use --all to fetch all {total} flows in one request"

    return title, tip


def build_update_payload(
    name: str | None,
    flow_type: FlowType | None,
    description: str | None,
    criteria: list[str] | None,
) -> dict[str, Any]:
    """Build update payload from provided fields."""
    payload: dict[str, Any] = {}
    if name is not None:
        payload["name"] = name
    if flow_type is not None:
        payload["type"] = flow_type.value
    if description is not None:
        payload["description"] = description
    if criteria is not None:
        payload["acceptance_criteria"] = list(criteria)
    return payload
