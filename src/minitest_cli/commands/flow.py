"""Testing flow commands: create, list, get, update, delete."""

from typing import Annotated, Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.flow_helpers import (
    FLOW_TABLE_HEADERS,
    FlowType,
    base_path,
    format_flow_row,
    format_pagination_info,
    get_app_flag,
    get_settings,
    handle_response_error,
    is_json_mode,
    run_api_call,
)
from minitest_cli.commands import flow_modify
from minitest_cli.core.app_context import resolve_app_id
from minitest_cli.core.auth import require_auth
from minitest_cli.utils.output import output, print_error, print_info, print_success, print_table

app = typer.Typer(name="flow", help="Testing flow operations.")

# Register update and delete commands from flow_modify module
app.command(name="update")(flow_modify.update_flow)
app.command(name="delete")(flow_modify.delete_flow)


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
    if not json_mode:
        print_success(f"Flow created: {data.get('id', '')}")
    output(data, json_mode=json_mode)


@app.command(name="list")
def list_flows(
    flow_type: Annotated[
        FlowType | None, typer.Option("--type", help="Filter by flow type.")
    ] = None,
    page: Annotated[int, typer.Option("--page", help="Page number.")] = 1,
    page_size: Annotated[int, typer.Option("--page-size", help="Items per page.")] = 20,
    all_flows: Annotated[
        bool, typer.Option("--all", help="Fetch all flows (ignores --page and --page-size).")
    ] = False,
) -> None:
    """List testing flows for the active app."""
    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)
    app_id = resolve_app_id(settings, get_app_flag())
    if all_flows:
        page, page_size = 1, 100  # API max page size

    params: dict[str, Any] = {"page": page, "page_size": page_size}
    if flow_type is not None:
        params["type"] = flow_type.value

    async def _run() -> Any:
        async with ApiClient(settings) as client:
            if not all_flows:
                resp = await client.get(base_path(app_id), params=params)
                handle_response_error(resp)
                return resp.json()

            items: list[dict[str, Any]] = []
            next_page = 1
            total: int | None = None
            while total is None or len(items) < total:
                resp = await client.get(
                    base_path(app_id),
                    params={**params, "page": next_page, "page_size": page_size},
                )
                handle_response_error(resp)
                body = resp.json()
                page_items = (
                    body if isinstance(body, list) else body.get("items", body.get("results", []))
                )
                items.extend(page_items)
                if isinstance(body, dict):
                    total = body.get("total")
                if not page_items or isinstance(body, list):
                    break
                next_page += 1
            return items

    data = run_api_call(_run())
    if json_mode:
        output(data, json_mode=True)
        return

    items = data if isinstance(data, list) else data.get("items", data.get("results", []))
    if not items:
        print_error("No flows found.")
        return

    if all_flows:
        title = f"Flows (showing all {len(items)} flows)"
        tip = None
    else:
        title, tip = format_pagination_info(data, page, page_size)
    rows = [format_flow_row(f) for f in items]
    print_table(FLOW_TABLE_HEADERS, rows, title=title)
    if tip:
        print_info(tip)


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
