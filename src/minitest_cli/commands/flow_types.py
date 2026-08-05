"""Flow type commands: list, create and update flow (user-story) types.

The CLI surface uses ``flow-types``; the backend endpoints are ``user-story-types``
for the built-ins and ``apps/{app_id}/custom-user-story-types`` for the tenant's
custom types (renamed in migrations 00050/00051). Custom types are tenant-scoped,
so the app in that path is only an addressing detail — see ``resolve_tenant_app_id``.
"""

import asyncio

import httpx
import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.api.errors import format_network_error
from minitest_cli.commands import flow_types_write
from minitest_cli.commands.flow_types_helpers import (
    BUILTIN_TYPES_PATH,
    EXIT_NETWORK_ERROR,
    get_app_flag,
    get_custom_flow_types,
    get_settings,
    handle_response_error,
    is_json_mode,
    resolve_tenant_app_id,
)
from minitest_cli.core.auth import require_auth
from minitest_cli.models.flow_type import FlowTypeListItem
from minitest_cli.utils.output import print_error, print_json

app = typer.Typer(name="flow-types", help="List, create and update flow (user-story) types.")


@app.callback()
def _callback() -> None:
    """Flow types operations."""


@app.command(name="list")
def list_flow_types() -> None:
    """List every flow (user-story) type value accepted by --type.

    Covers the built-in types plus your tenant's custom ones. --json carries the
    custom types' id, icon, color and usage prompt; plain output is names only.
    """
    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)

    async def _run() -> list[FlowTypeListItem]:
        async with ApiClient(settings) as client:
            resp = await client.get(BUILTIN_TYPES_PATH)
            handle_response_error(resp)
            builtin_types = resp.json()
            if not isinstance(builtin_types, list):
                print_error("Unexpected response shape: expected a JSON array.")
                raise typer.Exit(code=EXIT_NETWORK_ERROR)
            app_id = await resolve_tenant_app_id(client, settings, get_app_flag())
            custom_types = await get_custom_flow_types(client, app_id)
            return [
                *(FlowTypeListItem.builtin(name) for name in builtin_types),
                *(FlowTypeListItem.from_custom(t) for t in custom_types),
            ]

    try:
        flow_types = asyncio.run(_run())
    except httpx.HTTPError as exc:
        print_error(format_network_error(exc))
        raise typer.Exit(code=EXIT_NETWORK_ERROR) from exc

    if json_mode:
        print_json(flow_types)
        return

    # One type per line, easy to pipe.
    for flow_type in flow_types:
        print(flow_type.name)  # noqa: T201


app.command(name="create")(flow_types_write.create_flow_type)
app.command(name="update")(flow_types_write.update_flow_type)
app.command(name="delete")(flow_types_write.delete_flow_type)
