"""`scenario-binding set-personas` / `list-personas`: who Mini plays in a scenario."""

from typing import Annotated, Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.persona_helpers import current_app_id, resolve_persona_id
from minitest_cli.commands.run_helpers import ensure_uuid
from minitest_cli.commands.user_story_helpers import (
    base_path,
    get_settings,
    handle_response_error,
    is_json_mode,
    run_api_call,
)
from minitest_cli.utils.output import output, print_error, print_info, print_table

DraftFeatureOption = Annotated[
    str | None,
    typer.Option(
        "--draft-feature",
        help="Draft feature (branch) ID: read or write the scenario on that branch instead "
        "of the main suite. Use the scenario's main ID.",
    ),
]


def _print(data: dict[str, Any]) -> None:
    if is_json_mode():
        output(data, json_mode=True)
        return
    items = data["items"]
    where = f" on draft feature {data['draftFeatureId']}" if data.get("draftFeatureId") else ""
    if not items:
        print_info(f"Scenario {data['userStoryId']} plays no persona{where}.")
        return
    rows = [[p["id"], p["name"], "on" if p["exclusiveUse"] else "off"] for p in items]
    print_table(["ID", "Persona", "Exclusive use"], rows, title=f"Personas{where}")


def set_personas(
    user_story_id: Annotated[str, typer.Argument(help="Scenario ID.")],
    personas: Annotated[
        list[str] | None,
        typer.Option("--persona", help="Persona ID or name (repeatable). Replaces the full set."),
    ] = None,
    clear: Annotated[
        bool, typer.Option("--clear", help="Unbind every persona; the scenario runs as New user.")
    ] = False,
    draft_feature: DraftFeatureOption = None,
) -> None:
    """Set the personas a scenario plays; Mini signs in with one of each one's test accounts."""
    if personas and clear:
        print_error("Use either --persona or --clear, not both.")
        raise typer.Exit(code=1)
    if not personas and not clear:
        print_error("Provide --persona <id|name> (repeatable) or --clear.")
        raise typer.Exit(code=1)
    if draft_feature is not None:
        ensure_uuid(draft_feature, kind="draft feature id")
    app_id = current_app_id()

    async def _run() -> dict[str, Any]:
        async with ApiClient(get_settings()) as client:
            ids = [await resolve_persona_id(client, app_id, ref) for ref in personas or []]
            resp = await client.put(
                f"{base_path(app_id)}/{user_story_id}/personas",
                json={"personaIds": ids, "draftFeatureId": draft_feature},
            )
            handle_response_error(resp)
            return resp.json()

    _print(run_api_call(_run()))


def list_personas(
    user_story_id: Annotated[str, typer.Argument(help="Scenario ID.")],
    draft_feature: DraftFeatureOption = None,
) -> None:
    """List the personas a scenario plays."""
    if draft_feature is not None:
        ensure_uuid(draft_feature, kind="draft feature id")
    app_id = current_app_id()
    params = {"draftFeatureId": draft_feature} if draft_feature else {}

    async def _run() -> dict[str, Any]:
        async with ApiClient(get_settings()) as client:
            resp = await client.get(f"{base_path(app_id)}/{user_story_id}/personas", params=params)
            handle_response_error(resp)
            return resp.json()

    _print(run_api_call(_run()))
