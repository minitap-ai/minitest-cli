"""Write commands for custom flow (user-story) types: create, update, delete."""

import asyncio
from typing import Annotated, Any

import httpx
import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.flow_types_helpers import (
    EXIT_NETWORK_ERROR,
    custom_types_path,
    get_app_flag,
    get_settings,
    handle_response_error,
    is_json_mode,
    resolve_custom_flow_type_id,
    resolve_tenant_app_id,
)
from minitest_cli.core.auth import require_auth
from minitest_cli.utils.confirm import confirm_or_exit
from minitest_cli.utils.output import output, print_error, print_success

NameOption = Annotated[str | None, typer.Option("--name", help="Display name.")]
IconOption = Annotated[str | None, typer.Option("--icon", help="Lucide icon name.")]
ColorOption = Annotated[str | None, typer.Option("--color", help="Tailwind color name.")]
UsagePromptOption = Annotated[
    str | None,
    typer.Option(
        "--usage-prompt",
        help="Context handed to the agent when it runs a story of this type.",
    ),
]


def _run_write(coro: Any) -> Any:
    try:
        return asyncio.run(coro)
    except httpx.HTTPError as exc:
        print_error(f"Network error: {exc}")
        raise typer.Exit(code=EXIT_NETWORK_ERROR) from exc


def create_flow_type(
    name: Annotated[str, typer.Option("--name", help="Display name of the custom flow type.")],
    icon: Annotated[str, typer.Option("--icon", help="Lucide icon name.")] = "tag",
    color: Annotated[str, typer.Option("--color", help="Tailwind color name.")] = "gray",
    usage_prompt: UsagePromptOption = None,
) -> None:
    """Create a custom flow type, usable as --type on any user-story command.

    Custom types are tenant-scoped: every app on your tenant can use them.
    """
    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)

    payload: dict[str, Any] = {"name": name, "icon": icon, "color": color}
    if usage_prompt is not None:
        payload["usagePrompt"] = usage_prompt

    async def _run() -> Any:
        async with ApiClient(settings) as client:
            app_id = await resolve_tenant_app_id(client, settings, get_app_flag())
            resp = await client.post(custom_types_path(app_id), json=payload)
            handle_response_error(resp)
            return resp.json()

    data = _run_write(_run())
    if not json_mode:
        print_success(f"Flow type created: {data.get('name', name)} ({data.get('id', '')})")
    output(data, json_mode=json_mode)


def update_flow_type(
    flow_type: Annotated[str, typer.Argument(help="Custom flow type name or id.")],
    name: NameOption = None,
    icon: IconOption = None,
    color: ColorOption = None,
    usage_prompt: UsagePromptOption = None,
) -> None:
    """Rename or restyle a custom flow type.

    Renaming keeps the type's identity, so user stories already on it stay on it.
    """
    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)

    payload: dict[str, Any] = {}
    for field, value in (
        ("name", name),
        ("icon", icon),
        ("color", color),
        ("usagePrompt", usage_prompt),
    ):
        if value is not None:
            payload[field] = value
    if not payload:
        print_error("Provide at least one field to update.")
        raise typer.Exit(code=1)

    async def _run() -> Any:
        async with ApiClient(settings) as client:
            app_id = await resolve_tenant_app_id(client, settings, get_app_flag())
            custom_type_id = await resolve_custom_flow_type_id(client, app_id, flow_type)
            resp = await client.patch(custom_types_path(app_id, custom_type_id), json=payload)
            handle_response_error(resp)
            return resp.json()

    data = _run_write(_run())
    if not json_mode:
        print_success(f"Flow type updated: {data.get('name', flow_type)} ({data.get('id', '')})")
    output(data, json_mode=json_mode)


def delete_flow_type(
    flow_type: Annotated[str, typer.Argument(help="Custom flow type name or id.")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Confirm the deletion.")] = False,
) -> None:
    """Delete a custom flow type.

    Every user story on that type is reset to the built-in `other` type.
    """
    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)
    confirm_or_exit(
        yes,
        f"Deleting flow type '{flow_type}' (its user stories are reset to 'other')",
    )

    async def _run() -> str:
        async with ApiClient(settings) as client:
            app_id = await resolve_tenant_app_id(client, settings, get_app_flag())
            custom_type_id = await resolve_custom_flow_type_id(client, app_id, flow_type)
            resp = await client.delete(custom_types_path(app_id, custom_type_id))
            handle_response_error(resp)
            return custom_type_id

    custom_type_id = _run_write(_run())
    if json_mode:
        output({"deleted": True, "id": custom_type_id}, json_mode=True)
    else:
        print_success(f"Flow type deleted: {flow_type} ({custom_type_id})")
