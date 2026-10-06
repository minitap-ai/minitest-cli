"""Tag commands: list, create, update, delete tenant scenario tags."""

from collections.abc import Callable, Coroutine
from typing import Annotated, Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.tags_helpers import fetch_tags, find_tag, tags_path
from minitest_cli.commands.user_story_helpers import (
    get_app_flag,
    get_settings,
    handle_response_error,
    is_json_mode,
    run_api_call,
)
from minitest_cli.core.app_context import resolve_app_id
from minitest_cli.core.auth import require_auth
from minitest_cli.models.tag import TagColor
from minitest_cli.utils.confirm import confirm_or_exit
from minitest_cli.utils.output import output, print_error, print_info, print_success, print_table

app = typer.Typer(name="tags", help="List, create, update and delete scenario tags.")

ColorOption = Annotated[TagColor | None, typer.Option("--color", help="Tag colour.")]
DescriptionOption = Annotated[
    str | None, typer.Option("--description", help="What the tag groups (max 2000 chars).")
]


def _call[T](action: Callable[[ApiClient, str], Coroutine[Any, Any, T]]) -> T:
    settings = get_settings()
    require_auth(settings)
    app_id = resolve_app_id(settings, get_app_flag())

    async def _run() -> T:
        async with ApiClient(settings) as client:
            return await action(client, app_id)

    return run_api_call(_run())


def _tag_fields(
    name: str | None, color: TagColor | None, description: str | None
) -> dict[str, Any]:
    fields = {"name": name, "color": color.value if color else None, "description": description}
    return {key: value for key, value in fields.items() if value is not None}


@app.command(name="list")
def list_tags() -> None:
    """List the tenant's tags with how many scenarios carry each."""
    tags = _call(fetch_tags)
    if is_json_mode():
        output(tags, json_mode=True)
        return
    if not tags:
        print_info("No tags yet. Create one with `minitest tags create --name <name>`.")
        return
    rows = [
        [t["name"], t.get("color", ""), str(t.get("scenarioCount", 0)), t.get("description") or ""]
        for t in tags
    ]
    print_table(["Name", "Color", "Scenarios", "Description"], rows, title="Tags")


@app.command(name="create")
def create_tag(
    name: Annotated[str, typer.Option("--name", help="Tag name (1-40 chars, no comma).")],
    color: ColorOption = None,
    description: DescriptionOption = None,
) -> None:
    """Create a tag, or return the existing one with the same name (case-insensitive)."""

    async def _create(client: ApiClient, app_id: str) -> tuple[bool, dict[str, Any]]:
        resp = await client.post(tags_path(app_id), json=_tag_fields(name, color, description))
        handle_response_error(resp, resource="Tag")
        return resp.status_code == 201, resp.json()

    created, tag = _call(_create)
    if not is_json_mode():
        verb = "created" if created else "already exists"
        print_success(f"Tag {verb}: {tag.get('name')} ({tag.get('id')})")
    output(tag, json_mode=is_json_mode())


@app.command(name="update")
def update_tag(
    tag_ref: Annotated[str, typer.Argument(help="Tag name or ID.")],
    name: Annotated[str | None, typer.Option("--name", help="New tag name.")] = None,
    color: ColorOption = None,
    description: DescriptionOption = None,
) -> None:
    """Rename a tag or change its colour or description."""
    payload = _tag_fields(name, color, description)
    if not payload:
        print_error("Provide at least one of --name, --color or --description.")
        raise typer.Exit(code=1)

    async def _update(client: ApiClient, app_id: str) -> dict[str, Any]:
        tag = find_tag(await fetch_tags(client, app_id), tag_ref)
        resp = await client.patch(f"{tags_path(app_id)}/{tag['id']}", json=payload)
        handle_response_error(resp, resource="Tag")
        return resp.json()

    tag = _call(_update)
    if not is_json_mode():
        print_success(f"Tag updated: {tag.get('name')}")
    output(tag, json_mode=is_json_mode())


@app.command(name="delete")
def delete_tag(
    tag_ref: Annotated[str, typer.Argument(help="Tag name or ID.")],
    yes: Annotated[bool, typer.Option("--yes", help="Confirm the deletion.")] = False,
) -> None:
    """Delete a tag and remove it from every scenario that carries it."""
    confirm_or_exit(yes, f"Deleting tag {tag_ref!r}")

    async def _delete(client: ApiClient, app_id: str) -> dict[str, Any]:
        tag = find_tag(await fetch_tags(client, app_id), tag_ref)
        resp = await client.delete(f"{tags_path(app_id)}/{tag['id']}")
        handle_response_error(resp, resource="Tag")
        return tag

    tag = _call(_delete)
    if is_json_mode():
        output({"deleted": True, "id": tag["id"], "name": tag["name"]}, json_mode=True)
    else:
        print_success(f"Tag deleted: {tag['name']}")
