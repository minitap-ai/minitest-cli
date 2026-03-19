"""Testing flow commands: create, list, get, update, delete."""

from typing import Annotated, Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.flow_helpers import (
    FLOW_TABLE_HEADERS,
    FlowType,
    base_path,
    format_flow_row,
    get_app_flag,
    get_settings,
    handle_response_error,
    is_json_mode,
    run_api_call,
)
from minitest_cli.core.app_context import resolve_app_id
from minitest_cli.core.auth import require_auth
from minitest_cli.utils.output import output, print_error, print_success, print_table

app = typer.Typer(name="flow", help="Testing flow operations.")


@app.command(name="create")
def create_flow(
    name: Annotated[str, typer.Option("--name", help="Flow name.")],
    flow_type: Annotated[FlowType, typer.Option("--type", help="Flow type.")],
    description: Annotated[
        str | None, typer.Option("--description", help="Flow description.")
    ] = None,
    criteria: Annotated[
        list[str] | None, typer.Option("--criteria", help="Acceptance criteria (repeatable).")
    ] = None,
) -> None:
    """Create a new testing flow."""
    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)
    app_id = resolve_app_id(settings, get_app_flag())

    payload: dict[str, Any] = {"name": name, "type": flow_type.value}
    if description is not None:
        payload["description"] = description
    if criteria:
        payload["acceptance_criteria"] = list(criteria)

    async def _run() -> dict[str, Any]:
        async with ApiClient(settings) as client:
            resp = await client.post(base_path(app_id), json=payload)
            handle_response_error(resp)
            return resp.json()

    data = run_api_call(_run())
    if json_mode:
        output(data, json_mode=True)
    else:
        print_success(f"Flow created: {data.get('id', '')}")
        output(data, json_mode=False)


@app.command(name="list")
def list_flows(
    flow_type: Annotated[
        FlowType | None, typer.Option("--type", help="Filter by flow type.")
    ] = None,
    page: Annotated[int, typer.Option("--page", help="Page number.")] = 1,
    page_size: Annotated[int, typer.Option("--page-size", help="Items per page.")] = 20,
) -> None:
    """List testing flows for the active app."""
    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)
    app_id = resolve_app_id(settings, get_app_flag())

    params: dict[str, Any] = {"page": page, "page_size": page_size}
    if flow_type is not None:
        params["type"] = flow_type.value

    async def _run() -> Any:
        async with ApiClient(settings) as client:
            resp = await client.get(base_path(app_id), params=params)
            handle_response_error(resp)
            return resp.json()

    data = run_api_call(_run())
    if json_mode:
        output(data, json_mode=True)
    else:
        items = data if isinstance(data, list) else data.get("items", data.get("results", []))
        if not items:
            print_error("No flows found.")
            return
        rows = [format_flow_row(f) for f in items]
        print_table(FLOW_TABLE_HEADERS, rows, title="Flows")


@app.command(name="get")
def get_flow(
    flow_id: Annotated[str, typer.Argument(help="Flow ID.")],
) -> None:
    """Show details for a specific testing flow."""
    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)
    app_id = resolve_app_id(settings, get_app_flag())

    async def _run() -> dict[str, Any]:
        async with ApiClient(settings) as client:
            resp = await client.get(f"{base_path(app_id)}/{flow_id}")
            handle_response_error(resp)
            return resp.json()

    output(run_api_call(_run()), json_mode=json_mode)


@app.command(name="update")
def update_flow(
    flow_id: Annotated[str, typer.Argument(help="Flow ID.")],
    name: Annotated[str | None, typer.Option("--name", help="New flow name.")] = None,
    flow_type: Annotated[FlowType | None, typer.Option("--type", help="New flow type.")] = None,
    description: Annotated[
        str | None, typer.Option("--description", help="New description.")
    ] = None,
    criteria: Annotated[
        list[str] | None,
        typer.Option("--criteria", help="Replace acceptance criteria (repeatable)."),
    ] = None,
    add_criteria: Annotated[
        list[str] | None,
        typer.Option("--add-criteria", help="Append acceptance criteria (repeatable)."),
    ] = None,
) -> None:
    """Update an existing testing flow (partial update)."""
    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)
    app_id = resolve_app_id(settings, get_app_flag())

    payload: dict[str, Any] = {}
    if name is not None:
        payload["name"] = name
    if flow_type is not None:
        payload["type"] = flow_type.value
    if description is not None:
        payload["description"] = description
    if criteria is not None:
        payload["acceptance_criteria"] = list(criteria)

    async def _run() -> dict[str, Any]:
        async with ApiClient(settings) as client:
            path = f"{base_path(app_id)}/{flow_id}"
            if add_criteria:
                get_resp = await client.get(path)
                handle_response_error(get_resp)
                current = get_resp.json()
                existing = current.get("acceptance_criteria") or []
                payload["acceptance_criteria"] = existing + list(add_criteria)
            resp = await client.patch(path, json=payload)
            handle_response_error(resp)
            return resp.json()

    data = run_api_call(_run())
    if json_mode:
        output(data, json_mode=True)
    else:
        print_success(f"Flow updated: {flow_id}")
        output(data, json_mode=False)


@app.command(name="delete")
def delete_flow(
    flow_id: Annotated[str, typer.Argument(help="Flow ID.")],
    force: Annotated[bool, typer.Option("--force", help="Skip confirmation.")] = False,
) -> None:
    """Delete a testing flow. Requires --force flag."""
    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)

    if not force:
        print_error("Deletion requires --force flag.")
        raise typer.Exit(code=1)

    app_id = resolve_app_id(settings, get_app_flag())

    async def _run() -> None:
        async with ApiClient(settings) as client:
            resp = await client.delete(f"{base_path(app_id)}/{flow_id}")
            handle_response_error(resp)

    run_api_call(_run())
    if json_mode:
        output({"deleted": True, "id": flow_id}, json_mode=True)
    else:
        print_success(f"Flow deleted: {flow_id}")
