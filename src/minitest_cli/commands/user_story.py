"""User-story commands: create, list, get, update, delete, suggest-deps."""

from typing import Annotated, Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands import user_story_modify, user_story_suggest
from minitest_cli.commands.user_story_helpers import (
    USER_STORY_TABLE_HEADERS,
    base_path,
    format_pagination_info,
    format_user_story_row,
    get_app_flag,
    get_settings,
    handle_response_error,
    is_json_mode,
    run_api_call,
    validate_user_story_type,
)
from minitest_cli.core.app_context import resolve_app_id
from minitest_cli.core.auth import require_auth
from minitest_cli.utils.output import output, print_error, print_info, print_success, print_table

app = typer.Typer(name="user-story", help="User-story operations.")

app.command(name="update")(user_story_modify.update_user_story)
app.command(name="delete")(user_story_modify.delete_user_story)
app.command(name="suggest-deps")(user_story_suggest.suggest_dependencies)


@app.command(name="create")
def create_user_story(
    name: Annotated[str, typer.Option("--name", help="User-story name.")],
    user_story_type: Annotated[str, typer.Option("--type", help="User-story type.")],
    description: Annotated[
        str | None, typer.Option("--description", help="User-story description.")
    ] = None,
    criteria: Annotated[
        list[str] | None, typer.Option("--criteria", help="Acceptance criteria (repeatable).")
    ] = None,
    depends_on: Annotated[
        list[str] | None,
        typer.Option(
            "--depends-on",
            help=(
                "Parent user-story IDs this story depends on (repeatable). "
                "Validated server-side after creation: same-app, no cycles, "
                "references must exist."
            ),
        ),
    ] = None,
) -> None:
    """Create a new user story.

    When you already know which flows gate this one, set ``--depends-on``
    here rather than calling ``suggest-deps`` afterwards — it's
    deterministic, free, and one fewer round trip.
    """
    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)
    app_id = resolve_app_id(settings, get_app_flag())
    validate_user_story_type(user_story_type, settings)
    payload: dict[str, Any] = {"name": name, "type": user_story_type}
    if description is not None:
        payload["description"] = description
    if criteria:
        payload["acceptance_criteria"] = list(criteria)

    async def _run() -> dict[str, Any]:
        async with ApiClient(settings) as client:
            resp = await client.post(base_path(app_id), json=payload)
            handle_response_error(resp)
            created = resp.json()
            # The create endpoint doesn't accept ``depends_on`` so we follow
            # up with a PATCH. There's a small window where the story exists
            # without deps; the validation still runs on the PATCH so a bad
            # dep list won't leave a half-applied state — only an unintended
            # ``depends_on=[]`` story that the user can re-update or delete.
            if depends_on:
                story_id = created.get("id")
                if not story_id:
                    print_error("Server did not return an id for the new user story.")
                    raise typer.Exit(code=1)
                patch_resp = await client.patch(
                    f"{base_path(app_id)}/{story_id}",
                    json={"dependsOn": list(depends_on)},
                )
                handle_response_error(patch_resp)
                return patch_resp.json()
            return created

    data = run_api_call(_run())
    if not json_mode:
        print_success(f"User story created: {data.get('id', '')}")
    output(data, json_mode=json_mode)


@app.command(name="list")
def list_user_stories(
    user_story_type: Annotated[
        str | None, typer.Option("--type", help="Filter by user-story type.")
    ] = None,
    page: Annotated[int, typer.Option("--page", min=1, help="Page number.")] = 1,
    page_size: Annotated[
        int, typer.Option("--page-size", min=1, max=100, help="Items per page.")
    ] = 20,
    all_stories: Annotated[
        bool,
        typer.Option("--all", help="Fetch all user stories (ignores --page and --page-size)."),
    ] = False,
) -> None:
    """List user stories for the active app."""
    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)
    app_id = resolve_app_id(settings, get_app_flag())
    if user_story_type is not None:
        validate_user_story_type(user_story_type, settings)
    if all_stories:
        page, page_size = 1, 100

    params: dict[str, Any] = {"page": page, "page_size": page_size}
    if user_story_type is not None:
        params["type"] = user_story_type

    async def _run() -> Any:
        async with ApiClient(settings) as client:
            if not all_stories:
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
        print_info("No user stories found.")
        return

    if all_stories:
        title = f"User stories (showing all {len(items)} user stories)"
        tip = None
    elif isinstance(data, dict):
        title, tip = format_pagination_info(data, page, page_size)
    else:
        title, tip = "User stories", None
    rows = [format_user_story_row(s) for s in items]
    print_table(USER_STORY_TABLE_HEADERS, rows, title=title)
    if tip:
        print_info(tip)


@app.command(name="get")
def get_user_story(
    user_story_id: Annotated[str, typer.Argument(help="User-story ID.")],
) -> None:
    """Show details for a specific user story."""
    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)
    app_id = resolve_app_id(settings, get_app_flag())

    async def _run() -> dict[str, Any]:
        async with ApiClient(settings) as client:
            resp = await client.get(f"{base_path(app_id)}/{user_story_id}")
            handle_response_error(resp)
            return resp.json()

    output(run_api_call(_run()), json_mode=json_mode)
