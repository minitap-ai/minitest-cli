"""Testing flow modification commands: update, delete."""

from typing import Annotated, Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.flow_helpers import (
    base_path,
    extract_criteria_strings,
    get_app_flag,
    get_settings,
    handle_response_error,
    is_json_mode,
    run_api_call,
    validate_flow_type,
)
from minitest_cli.core.app_context import resolve_app_id
from minitest_cli.core.auth import require_auth
from minitest_cli.models.flow_template import UpdateFlowTemplateRequest
from minitest_cli.utils.output import output, print_error, print_success


def update_flow(
    flow_id: Annotated[str, typer.Argument(help="Flow ID.")],
    name: Annotated[str | None, typer.Option("--name", help="New flow name.")] = None,
    flow_type: Annotated[str | None, typer.Option("--type", help="New flow type.")] = None,
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

    if criteria is not None and add_criteria is not None:
        print_error("Use either --criteria or --add-criteria, not both.")
        raise typer.Exit(code=1)

    if flow_type is not None:
        validate_flow_type(flow_type, settings)

    req = UpdateFlowTemplateRequest(
        name=name,
        type=flow_type,
        description=description,
        acceptance_criteria=list(criteria) if criteria is not None else None,
    )
    if not req.has_changes() and not add_criteria:
        print_error("Provide at least one field to update.")
        raise typer.Exit(code=1)

    payload = req.to_payload()

    async def _run() -> dict[str, Any]:
        async with ApiClient(settings) as client:
            path = f"{base_path(app_id)}/{flow_id}"
            if add_criteria:
                get_resp = await client.get(path)
                handle_response_error(get_resp)
                existing = extract_criteria_strings(get_resp.json())
                payload["acceptanceCriteria"] = existing + list(add_criteria)
            resp = await client.patch(path, json=payload)
            handle_response_error(resp)
            return resp.json()

    data = run_api_call(_run())
    if not json_mode:
        print_success(f"Flow updated: {flow_id}")
    output(data, json_mode=json_mode)


def delete_flow(
    flow_id: Annotated[str, typer.Argument(help="Flow ID.")],
    force: Annotated[bool, typer.Option("--force", help="Skip confirmation.")] = False,
) -> None:
    """Delete a testing flow. Requires --force flag."""
    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)
    if not force:
        print_error("Delete requires --force flag.")
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
