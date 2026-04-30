"""Helpers for app-knowledge commands: error mapping and HTTP calls."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

import httpx
import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.core.config import Settings
from minitest_cli.utils.output import print_error

EXIT_GENERAL_ERROR = 1
EXIT_NETWORK_ERROR = 3
EXIT_NOT_FOUND = 4


def _extract_detail(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        if isinstance(body, dict):
            detail = body.get("detail") or body.get("message")
            if detail:
                return str(detail)
    except Exception:  # noqa: BLE001
        pass
    return resp.text or f"HTTP {resp.status_code}"


def _handle_response_error(resp: httpx.Response, *, resource: str = "App") -> None:
    if resp.status_code < 400:
        return
    detail = _extract_detail(resp)
    if resp.status_code == 404:
        print_error(f"{resource} not found: {detail}")
        raise typer.Exit(code=EXIT_NOT_FOUND)
    if resp.status_code in (401, 403):
        print_error(f"Authentication failed ({resp.status_code}): {detail}")
        raise typer.Exit(code=EXIT_GENERAL_ERROR)
    if 400 <= resp.status_code < 500:
        print_error(f"Validation error ({resp.status_code}): {detail}")
        raise typer.Exit(code=EXIT_GENERAL_ERROR)
    print_error(f"Backend error ({resp.status_code}): {detail}")
    raise typer.Exit(code=EXIT_NETWORK_ERROR)


def _run_api_call[T](coro: Coroutine[Any, Any, T]) -> T:
    try:
        return asyncio.run(coro)
    except httpx.HTTPError as exc:
        print_error(f"Network error: {exc}")
        raise typer.Exit(code=EXIT_NETWORK_ERROR) from exc


def fetch_app_knowledge(settings: Settings, app_id: str) -> dict[str, Any]:
    """Read the current AppKnowledge for an app.

    testing-service has no dedicated GET endpoint, so we read the test-config
    record (which carries the latest ``app_knowledge`` content) and surface a
    minimal ``{appId, content}`` shape for callers.
    """

    async def _run() -> dict[str, Any]:
        async with ApiClient(settings) as client:
            resp = await client.get(f"/api/v1/apps/{app_id}/test-config")
            _handle_response_error(resp)
            payload = resp.json()
            content: Any = None
            if isinstance(payload, dict):
                content = payload.get("appKnowledge") or payload.get("app_knowledge")
            return {"appId": app_id, "content": content}

    return _run_api_call(_run())


def update_app_knowledge(settings: Settings, app_id: str, content: str) -> dict[str, Any]:
    """Push a new AppKnowledge version for an app.

    Calls ``PUT /api/v1/apps/{app_id}/app-knowledge`` with body
    ``{"content": ...}`` and returns the parsed response.
    """

    async def _run() -> dict[str, Any]:
        async with ApiClient(settings) as client:
            resp = await client.put(
                f"/api/v1/apps/{app_id}/app-knowledge",
                json={"content": content},
            )
            _handle_response_error(resp)
            data = resp.json()
            if not isinstance(data, dict):
                print_error("Unexpected response shape from update endpoint.")
                raise typer.Exit(code=EXIT_NETWORK_ERROR)
            return data

    return _run_api_call(_run())
