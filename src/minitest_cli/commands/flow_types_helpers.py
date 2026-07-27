"""Shared helpers for flow (user-story) types: API paths, fetching, name resolution."""

import asyncio
from typing import NamedTuple
from uuid import UUID

import httpx
import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.core.config import Settings
from minitest_cli.models.app import AppListResponse
from minitest_cli.models.flow_type import CustomFlowType
from minitest_cli.utils.output import print_error

EXIT_NETWORK_ERROR = 3
EXIT_NOT_FOUND = 4

APPS_PATH = "/api/v1/apps"
BUILTIN_TYPES_PATH = "/api/v1/user-story-types"
CUSTOM_TYPE_VALUE = "custom"


def custom_types_path(app_id: str, custom_type_id: str | None = None) -> str:
    """Path of the tenant's custom flow types, or of one of them."""
    path = f"/api/v1/apps/{app_id}/custom-user-story-types"
    return f"{path}/{custom_type_id}" if custom_type_id else path


def extract_detail(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        if isinstance(body, dict):
            detail = body.get("detail") or body.get("message")
            if detail:
                return str(detail)
    except Exception:  # noqa: BLE001
        pass
    return resp.text or f"HTTP {resp.status_code}"


def handle_response_error(resp: httpx.Response) -> None:
    if resp.status_code < 400:
        return
    detail = extract_detail(resp)
    if resp.status_code in (401, 403):
        print_error(f"Authentication failed ({resp.status_code}): {detail}")
        raise typer.Exit(code=1)
    print_error(f"API error ({resp.status_code}): {detail}")
    raise typer.Exit(code=EXIT_NETWORK_ERROR)


def fetch_builtin_flow_types(settings: Settings) -> list[str]:
    """Fetch the built-in flow type values from the API."""
    try:
        resp = httpx.get(f"{settings.api_url}{BUILTIN_TYPES_PATH}", timeout=10)
    except httpx.HTTPError as exc:
        print_error(f"Failed to fetch flow types: {exc}")
        raise typer.Exit(code=EXIT_NETWORK_ERROR) from exc
    if resp.status_code != 200:
        print_error(f"Failed to fetch flow types: HTTP {resp.status_code}")
        raise typer.Exit(code=EXIT_NETWORK_ERROR)
    data = resp.json()
    if not isinstance(data, list) or not data:
        print_error("Invalid response from the flow types endpoint.")
        raise typer.Exit(code=EXIT_NETWORK_ERROR)
    return data


def get_settings() -> Settings:
    return typer.Context.settings  # type: ignore[attr-defined]


def is_json_mode() -> bool:
    return typer.Context.json_mode  # type: ignore[attr-defined]


def get_app_flag() -> str | None:
    return typer.Context.app_flag  # type: ignore[attr-defined]


async def resolve_tenant_app_id(client: ApiClient, settings: Settings, app_flag: str | None) -> str:
    """Return an app id to address the tenant's custom flow types.

    Custom types are tenant-scoped but the endpoint is nested under an app, so any
    app of the tenant works and the caller does not have to target one.
    """
    targeted = app_flag or settings.app_id
    if targeted:
        return targeted

    resp = await client.get(APPS_PATH)
    handle_response_error(resp)
    apps = AppListResponse.model_validate(resp.json()).apps
    if not apps:
        # App-scoped API keys can list no app at all, so point at the flag first.
        print_error(
            "Could not resolve an app to reach your flow types. "
            "Pass --app <id> or set MINITEST_APP_ID."
        )
        raise typer.Exit(code=EXIT_NOT_FOUND)
    tenant_ids = {a.tenant_id for a in apps}
    if len(tenant_ids) > 1:
        print_error(
            f"Your account spans {len(tenant_ids)} tenants. "
            "Pass --app <id> to pick the one to act on."
        )
        raise typer.Exit(code=1)
    return apps[0].id


async def get_custom_flow_types(client: ApiClient, app_id: str) -> list[CustomFlowType]:
    """Fetch the tenant's custom flow types on an already-open client."""
    resp = await client.get(custom_types_path(app_id))
    handle_response_error(resp)
    data = resp.json()
    if not isinstance(data, list):
        print_error("Unexpected response shape: expected a JSON array of custom flow types.")
        raise typer.Exit(code=EXIT_NETWORK_ERROR)
    return [CustomFlowType.model_validate(item) for item in data]


async def resolve_custom_flow_type_id(client: ApiClient, app_id: str, selector: str) -> str:
    """Resolve a custom flow type id from either an id or a (case-insensitive) name."""
    try:
        return str(UUID(selector))
    except ValueError:
        pass

    custom_types = await get_custom_flow_types(client, app_id)
    for custom_type in custom_types:
        if custom_type.name.lower() == selector.lower():
            return custom_type.id

    known = ", ".join(t.name for t in custom_types) or "none"
    print_error(f"No custom flow type named '{selector}'. Existing custom types: {known}")
    raise typer.Exit(code=EXIT_NOT_FOUND)


def fetch_custom_flow_types(settings: Settings, app_id: str) -> list[CustomFlowType]:
    """Fetch the tenant's custom flow types from a synchronous command body."""

    async def _run() -> list[CustomFlowType]:
        async with ApiClient(settings) as client:
            return await get_custom_flow_types(client, app_id)

    try:
        return asyncio.run(_run())
    except httpx.HTTPError as exc:
        print_error(f"Failed to fetch custom flow types: {exc}")
        raise typer.Exit(code=EXIT_NETWORK_ERROR) from exc


class ResolvedFlowType(NamedTuple):
    """A ``--type`` value resolved into the fields the user-story API expects."""

    value: str
    custom_type_id: str | None


def resolve_flow_type(value: str, settings: Settings, app_id: str) -> ResolvedFlowType:
    """Resolve a ``--type`` value against built-in types, then the tenant's custom ones.

    Custom types resolve to the ``custom`` API type plus the matching type id, which
    is what testing-service expects — the custom name itself is not a valid API value.
    """
    builtin_types = fetch_builtin_flow_types(settings)
    if value in builtin_types:
        return ResolvedFlowType(value, None)

    custom_types = fetch_custom_flow_types(settings, app_id)
    for custom_type in custom_types:
        if custom_type.name.lower() == value.lower():
            return ResolvedFlowType(CUSTOM_TYPE_VALUE, custom_type.id)

    valid = [*builtin_types, *(t.name for t in custom_types)]
    print_error(f"Invalid flow type '{value}'. Valid types: {', '.join(valid)}")
    raise typer.Exit(code=1)
