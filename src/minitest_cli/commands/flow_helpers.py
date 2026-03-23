"""Shared helpers for flow commands: API paths, response handling, formatting."""

import asyncio
from collections.abc import Coroutine
from typing import Any

import httpx
import typer

from minitest_cli.core.config import Settings
from minitest_cli.models.flow_template import (
    FlowTemplateDetailResponse,
    FlowTemplateListResponse,
)
from minitest_cli.utils.output import print_error

EXIT_NETWORK_ERROR = 3
EXIT_NOT_FOUND = 4

FLOW_TABLE_HEADERS = ["ID", "Name", "Type", "Description", "Acceptance Criteria"]


def fetch_flow_types(settings: Settings) -> list[str]:
    """Fetch valid flow types from the API."""
    try:
        resp = httpx.get(
            f"{settings.api_url}/api/v1/flow-types",
            timeout=10,
        )
    except httpx.HTTPError as exc:
        print_error(f"Failed to fetch flow types: {exc}")
        raise typer.Exit(code=EXIT_NETWORK_ERROR) from exc
    if resp.status_code != 200:
        print_error(f"Failed to fetch flow types: HTTP {resp.status_code}")
        raise typer.Exit(code=EXIT_NETWORK_ERROR)
    data = resp.json()
    if not isinstance(data, list) or not data:
        print_error("Invalid response from flow types endpoint.")
        raise typer.Exit(code=EXIT_NETWORK_ERROR)
    return data


def validate_flow_type(value: str, settings: Settings) -> str:
    """Validate a flow type value against types from the API."""
    valid = fetch_flow_types(settings)
    if value not in valid:
        print_error(f"Invalid flow type '{value}'. Valid types: {', '.join(valid)}")
        raise typer.Exit(code=1)
    return value


def get_settings() -> Settings:
    return typer.Context.settings  # type: ignore[attr-defined]


def is_json_mode() -> bool:
    return typer.Context.json_mode  # type: ignore[attr-defined]


def get_app_flag() -> str | None:
    return typer.Context.app_flag  # type: ignore[attr-defined]


def base_path(app_id: str) -> str:
    return f"/api/v1/apps/{app_id}/flow-templates"


def extract_detail(resp: httpx.Response) -> str | None:
    try:
        body = resp.json()
        if isinstance(body, dict):
            return body.get("detail") or body.get("message")
    except Exception:  # noqa: BLE001
        pass
    return None


def handle_response_error(resp: httpx.Response, *, resource: str = "Flow") -> None:
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


def format_flow_row(flow: dict[str, Any]) -> list[str]:
    criteria_str = ""
    try:
        parsed = FlowTemplateDetailResponse.model_validate(flow)
        criteria_str = "; ".join(c.content for c in parsed.acceptance_criteria)
    except Exception:  # noqa: BLE001
        pass
    return [
        str(flow.get("id", "")),
        flow.get("name", ""),
        flow.get("type", ""),
        flow.get("description", "") or "",
        criteria_str,
    ]


def extract_criteria_strings(flow_data: dict[str, Any]) -> list[str]:
    """Extract plain-text criteria from a flow response, handling all formats."""
    raw = flow_data.get("acceptanceCriteria") or flow_data.get("acceptance_criteria") or []
    return [
        item.get("content", "") if isinstance(item, dict) else str(item)
        for item in raw
        if (item.get("content") if isinstance(item, dict) else item)
    ]


def format_pagination_info(
    data: dict[str, Any],
    page: int,
    page_size: int,
) -> tuple[str, str | None]:
    try:
        parsed = FlowTemplateListResponse.model_validate(data)
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

    title = f"Flows (Page {current_page} of {total_pages}, showing {start}-{end} of {total})"

    tip = None
    if current_page < total_pages:
        next_page = current_page + 1
        tip = f"\n💡 Tip: Use --page {next_page} to see more, or --all to fetch all {total} flows"
    elif total > current_page_size and current_page_size < 100:
        tip = f"\n💡 Tip: Use --all to fetch all {total} flows in one request"

    return title, tip
