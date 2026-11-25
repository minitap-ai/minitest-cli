"""`minitest persona`: who Mini plays in a scenario, and its pool of test accounts."""

from enum import StrEnum
from typing import Annotated, Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands import persona_default
from minitest_cli.commands.persona_helpers import (
    current_app_id,
    ACCOUNT_TABLE_HEADERS,
    PERSONA_TABLE_HEADERS,
    POOL_TABLE_HEADERS,
    format_account_row,
    format_persona_row,
    format_pool_row,
    handle_persona_response,
    personas_path,
    resolve_persona_id,
)
from minitest_cli.commands.test_account_helpers import (
    get_settings,
    is_json_mode,
    run_api_call,
)
from minitest_cli.utils.output import output, print_error, print_info, print_success, print_table

app = typer.Typer(
    name="persona",
    help="Manage personas: who Mini plays in a scenario (e.g. 'Denmark buyer'). "
    "Each persona has one or more test accounts (`minitest test-account`).",
)
persona_default.register(app)

PersonaArg = Annotated[str, typer.Argument(help="Persona ID or name.")]


class Switch(StrEnum):
    ON = "on"
    OFF = "off"


async def _persona_call(ref: str, method: str, suffix: str = "", **kwargs: Any) -> Any:
    app_id = current_app_id()
    async with ApiClient(get_settings()) as client:
        persona_id = await resolve_persona_id(client, app_id, ref)
        resp = await client.request(
            method, f"{personas_path(app_id)}/{persona_id}{suffix}", **kwargs
        )
        handle_persona_response(resp)
        return resp.json() if resp.content else {"id": persona_id}


@app.command(name="list")
def list_personas() -> None:
    """List the app's personas with their test accounts and scenarios."""
    app_id = current_app_id()

    async def _run() -> Any:
        async with ApiClient(get_settings()) as client:
            resp = await client.get(personas_path(app_id))
            handle_persona_response(resp)
            return resp.json()["items"]

    items = run_api_call(_run())
    if is_json_mode():
        output(items, json_mode=True)
    elif not items:
        print_info("No personas yet. Create one with `minitest persona create --name ...`.")
    else:
        rows = [format_persona_row(p) for p in items]
        print_table(PERSONA_TABLE_HEADERS, rows, title=f"Personas ({len(items)})")


@app.command(name="get")
def get_persona(persona: PersonaArg) -> None:
    """Show a persona and its test accounts (credentials are never shown)."""
    data = run_api_call(_persona_call(persona, "GET"))
    if is_json_mode():
        output(data, json_mode=True)
        return
    print_table(PERSONA_TABLE_HEADERS, [format_persona_row(data)], title=data["name"])
    if data.get("about"):
        print_info(data["about"])
    rows = [format_account_row(a) for a in data["accounts"]]
    print_table(ACCOUNT_TABLE_HEADERS, rows, title=f"Test accounts ({len(rows)})")


@app.command(name="pool")
def pool(persona: PersonaArg) -> None:
    """Show which test accounts of a persona are free, in use, or cooling down."""
    data = run_api_call(_persona_call(persona, "GET", "/pool"))
    if is_json_mode():
        output(data, json_mode=True)
        return
    counts = data["persona"]
    title = (
        f"{counts['name']}: {counts['freeCount']} free, {counts['inUseCount']} in use, "
        f"{counts['coolingDownCount']} cooling down"
    )
    print_table(POOL_TABLE_HEADERS, [format_pool_row(e) for e in data["accounts"]], title=title)


@app.command(name="create")
def create_persona(
    name: Annotated[str, typer.Option("--name", help="Persona name, unique in the app.")],
    about: Annotated[str | None, typer.Option("--about", help="Who this persona is.")] = None,
    exclusive: Annotated[
        bool,
        typer.Option(
            "--exclusive",
            help="Exclusive use: each test account is used by one run at a time.",
        ),
    ] = False,
) -> None:
    """Create a persona, then add its test accounts with `minitest test-account add`."""
    app_id = current_app_id()
    body = {"name": name, "about": about, "exclusiveUse": exclusive}

    async def _run() -> Any:
        async with ApiClient(get_settings()) as client:
            resp = await client.post(personas_path(app_id), json=body)
            handle_persona_response(resp)
            return resp.json()

    data = run_api_call(_run())
    if not is_json_mode():
        print_success(
            f"Persona created: {data['id']}. Add a test account with "
            f"`minitest test-account add --persona {data['id']} ...`."
        )
    output(data, json_mode=is_json_mode())


@app.command(name="update")
def update_persona(
    persona: PersonaArg,
    name: Annotated[str | None, typer.Option("--name", help="New name.")] = None,
    about: Annotated[str | None, typer.Option("--about", help="New notes.")] = None,
    clear_about: Annotated[bool, typer.Option("--clear-about", help="Remove the notes.")] = False,
) -> None:
    """Rename a persona or edit its notes."""
    if about is not None and clear_about:
        print_error("Use either --about or --clear-about, not both.")
        raise typer.Exit(code=1)
    body: dict[str, Any] = {}
    if name is not None:
        body["name"] = name
    if about is not None or clear_about:
        body["about"] = about
    if not body:
        print_error("Provide --name, --about or --clear-about.")
        raise typer.Exit(code=1)
    data = run_api_call(_persona_call(persona, "PATCH", json=body))
    if not is_json_mode():
        print_success(f"Persona updated: {data['id']}")
    output(data, json_mode=is_json_mode())


@app.command(name="exclusive")
def set_exclusive(
    persona: PersonaArg,
    state: Annotated[Switch, typer.Argument(help="on: one run at a time per test account.")],
) -> None:
    """Turn exclusive use on or off. On: add test accounts to run more scenarios in parallel."""
    body = {"exclusiveUse": state is Switch.ON}
    data = run_api_call(_persona_call(persona, "PUT", "/exclusive-use", json=body))
    if not is_json_mode():
        print_success(f"Exclusive use {state.value} for {data['name']}.")
    output(data, json_mode=is_json_mode())


@app.command(name="delete")
def delete_persona(
    persona: PersonaArg,
    force: Annotated[bool, typer.Option("--force", help="Skip confirmation.")] = False,
) -> None:
    """Delete a persona that no scenario plays and that has no test account left."""
    if not force:
        print_error("Delete requires --force flag.")
        raise typer.Exit(code=1)
    data = run_api_call(_persona_call(persona, "DELETE"))
    if is_json_mode():
        output({"deleted": True, "id": data["id"]}, json_mode=True)
    else:
        print_success(f"Persona deleted: {data['id']}")
