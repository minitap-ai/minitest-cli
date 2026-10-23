"""Shared plumbing for `minitest schedules`: API paths, error handling, lookup by name or id."""

from collections.abc import Callable, Coroutine
from typing import Any

import httpx
import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands._response_errors import (
    EXIT_NETWORK_ERROR,
    EXIT_NOT_FOUND,
    extract_detail,
)
from minitest_cli.commands.user_story_helpers import get_app_flag, get_settings, run_api_call
from minitest_cli.core.app_context import resolve_app_id
from minitest_cli.core.auth import require_auth
from minitest_cli.utils.output import print_error

UNAVAILABLE_MESSAGE = "Scheduled runs are not available on this workspace yet."
# The body of a path no route matches, as opposed to "Schedule not found".
_NO_ROUTE_DETAIL = "Not Found"


def schedules_path(app_id: str) -> str:
    return f"/api/v1/apps/{app_id}/schedules"


def check_response(resp: httpx.Response) -> None:
    if resp.status_code < 400:
        return
    detail = extract_detail(resp).strip()
    if resp.status_code == 404:
        unavailable = ("", _NO_ROUTE_DETAIL, UNAVAILABLE_MESSAGE.rstrip("."))
        known = _is_json(resp) and detail.rstrip(".") not in unavailable
        print_error(detail if known else UNAVAILABLE_MESSAGE)
        raise typer.Exit(code=EXIT_NOT_FOUND)
    print_error(f"API error ({resp.status_code}): {detail}")
    raise typer.Exit(code=EXIT_NETWORK_ERROR)


def _is_json(resp: httpx.Response) -> bool:
    try:
        return isinstance(resp.json(), dict)
    except ValueError:
        return False


def call_api[T](action: Callable[[ApiClient, str], Coroutine[Any, Any, T]]) -> T:
    settings = get_settings()
    require_auth(settings)
    app_id = resolve_app_id(settings, get_app_flag())

    async def _run() -> T:
        async with ApiClient(settings) as client:
            return await action(client, app_id)

    return run_api_call(_run())


async def fetch_schedules(client: ApiClient, app_id: str) -> list[dict[str, Any]]:
    resp = await client.get(schedules_path(app_id))
    check_response(resp)
    return resp.json()


async def resolve_schedule(client: ApiClient, app_id: str, ref: str) -> dict[str, Any]:
    schedules = await fetch_schedules(client, app_id)
    wanted = ref.strip().casefold()
    for schedule in schedules:
        if schedule.get("id") == ref or str(schedule.get("name", "")).casefold() == wanted:
            return schedule
    known = ", ".join(str(s.get("name")) for s in schedules) or "none"
    print_error(f"Schedule not found: {ref}. Known schedules: {known}.")
    raise typer.Exit(code=EXIT_NOT_FOUND)


async def send(
    client: ApiClient, method: str, path: str, *, json: Any = None, **kwargs: Any
) -> Any:
    resp = await client.request(method, path, json=json, **kwargs)
    check_response(resp)
    return None if resp.status_code == 204 else resp.json()
