"""Helpers for app commands: error mapping and apps-manager request helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import typer

from minitest_cli.api.apps_manager_client import AppsManagerClient
from minitest_cli.core.config import Settings
from minitest_cli.models.app import AppDetailResponse
from minitest_cli.utils.output import print_error

EXIT_GENERAL_ERROR = 1
EXIT_NETWORK_ERROR = 3
EXIT_NOT_FOUND = 4

_IMAGE_EXTENSIONS = {"png", "jpeg", "jpg", "webp", "gif", "svg"}


def extract_backend_detail(resp: httpx.Response) -> str:
    """Extract a human-readable error detail from an apps-manager response."""
    try:
        body = resp.json()
        if isinstance(body, dict):
            detail = body.get("detail") or body.get("message")
            if detail:
                return str(detail)
    except Exception:  # noqa: BLE001
        pass
    return resp.text or f"HTTP {resp.status_code}"


def handle_create_response_error(resp: httpx.Response) -> None:
    """Map a non-2xx apps-manager response to an exit code with a clean message."""
    if resp.status_code < 400:
        return

    detail = extract_backend_detail(resp)
    if resp.status_code == 404:
        print_error(f"Not found: {detail}")
        raise typer.Exit(code=EXIT_NOT_FOUND)
    if resp.status_code in (401, 403):
        print_error(f"Authentication failed ({resp.status_code}): {detail}")
        raise typer.Exit(code=EXIT_GENERAL_ERROR)
    if 400 <= resp.status_code < 500:
        print_error(f"Validation error ({resp.status_code}): {detail}")
        raise typer.Exit(code=EXIT_GENERAL_ERROR)
    print_error(f"Backend error ({resp.status_code}): {detail}")
    raise typer.Exit(code=EXIT_NETWORK_ERROR)


def _icon_content_type(icon: Path) -> str:
    """Best-effort content type from extension; apps-manager only checks truthiness."""
    suffix = icon.suffix.lower().lstrip(".")
    if suffix in _IMAGE_EXTENSIONS:
        return f"image/{'jpeg' if suffix == 'jpg' else suffix}"
    return "application/octet-stream"


async def create_app_request(
    settings: Settings,
    *,
    tenant_id: str,
    name: str,
    description: str | None,
    slug: str | None,
    icon: Path | None,
) -> AppDetailResponse:
    """Send the multipart POST to apps-manager and return the parsed response."""
    data: dict[str, str] = {"name": name}
    if description is not None:
        data["description"] = description
    if slug is not None:
        data["slug"] = slug

    files: dict[str, Any] = {}
    icon_handle = None
    try:
        if icon is not None:
            icon_handle = icon.open("rb")
            files["icon"] = (icon.name, icon_handle, _icon_content_type(icon))

        async with AppsManagerClient(settings) as client:
            resp = await client.upload_form(
                f"/api/v1/tenants/{tenant_id}/apps",
                data=data,
                files=files,
            )
    finally:
        if icon_handle is not None:
            icon_handle.close()

    handle_create_response_error(resp)
    return AppDetailResponse.model_validate(resp.json())
