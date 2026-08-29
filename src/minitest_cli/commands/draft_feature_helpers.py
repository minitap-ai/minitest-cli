"""Shared helpers for draft-feature commands: API paths, response handling, formatting."""

import json
from pathlib import Path
from typing import Any

import httpx
import typer

from minitest_cli.models.draft_feature import DraftFeatureResponse
from minitest_cli.utils.output import print_error

EXIT_GENERAL_ERROR = 1
EXIT_NETWORK_ERROR = 3
EXIT_NOT_FOUND = 4

DRAFT_FEATURE_TABLE_HEADERS = ["ID", "Title", "Status", "Rebase", "Description"]
CHANGESET_TABLE_HEADERS = ["#", "Op", "Payload"]
EFFECTIVE_STORY_HEADERS = ["Ordinal", "Story ID", "Slot ID", "Origin"]
EFFECTIVE_EDGE_HEADERS = ["Child Story ID", "Parent Story ID"]
CREATED_STORY_HEADERS = ["tmpId", "Story ID"]


def base_path(app_id: str) -> str:
    return f"/api/v1/apps/{app_id}/draft-features"


def extract_detail(resp: httpx.Response) -> str | None:
    try:
        body = resp.json()
        if isinstance(body, dict):
            return body.get("detail") or body.get("message")
    except Exception:  # noqa: BLE001
        pass
    return None


def handle_response_error(resp: httpx.Response, *, resource: str = "Draft feature") -> None:
    if resp.status_code == 404:
        detail = extract_detail(resp)
        print_error(detail or f"{resource} not found.")
        raise typer.Exit(code=EXIT_NOT_FOUND)
    if resp.status_code >= 400:
        detail = extract_detail(resp)
        print_error(detail or f"API error: {resp.status_code}")
        raise typer.Exit(code=EXIT_NETWORK_ERROR)


def format_draft_feature_row(feature: DraftFeatureResponse) -> list[str]:
    return [
        feature.id,
        feature.title,
        feature.status.value,
        feature.rebase_state.value,
        feature.description,
    ]


def format_changeset_op_row(index: int, op: dict[str, Any]) -> list[str]:
    payload = {key: value for key, value in op.items() if key != "op"}
    return [str(index), str(op.get("op", "")), json.dumps(payload, default=str)]


def read_changeset_file(path: Path) -> dict[str, Any]:
    """Load an apply request body from disk, refusing anything the API cannot accept."""
    try:
        payload = json.loads(path.read_text())
    except OSError as exc:
        print_error(f"Could not read changeset file '{path}': {exc}")
        raise typer.Exit(code=EXIT_GENERAL_ERROR) from exc
    except json.JSONDecodeError as exc:
        print_error(f"Changeset file '{path}' is not valid JSON: {exc}")
        raise typer.Exit(code=EXIT_GENERAL_ERROR) from exc
    if not isinstance(payload, dict):
        print_error(
            f"Changeset file '{path}' must contain a JSON object "
            "({'expectedMainRev': ..., 'ops': [...]}), not a "
            f"{type(payload).__name__}."
        )
        raise typer.Exit(code=EXIT_GENERAL_ERROR)
    return payload
