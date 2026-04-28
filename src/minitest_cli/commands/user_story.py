"""User-story commands: create, list, get, update, delete, suggest-deps."""

import sys
from collections import defaultdict
from typing import Annotated, Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands import user_story_modify
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
from minitest_cli.models.user_story import SuggestDependenciesResponse
from minitest_cli.utils.output import (
    output,
    print_error,
    print_info,
    print_success,
    print_table,
    print_warning,
)

app = typer.Typer(name="user-story", help="User-story operations.")

app.command(name="update")(user_story_modify.update_user_story)
app.command(name="delete")(user_story_modify.delete_user_story)


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


@app.command(name="suggest-deps")
def suggest_dependencies(
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            "-y",
            help="Apply every suggestion without prompting. Required in non-TTY contexts.",
        ),
    ] = False,
) -> None:
    """Ask the agent to propose user-story dependencies for this app.

    Fallback for the case where you genuinely don't know what the deps
    should be. **Prefer setting ``--depends-on`` directly on ``create`` /
    ``update``** when you can reason about the dep yourself — it's
    cheaper, deterministic, and avoids the LLM round-trip. Use this
    command to seed an initial graph or when reviewing an unfamiliar app.
    """
    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)
    app_id = resolve_app_id(settings, get_app_flag())

    async def _suggest() -> SuggestDependenciesResponse:
        async with ApiClient(settings) as client:
            resp = await client.post(
                f"{base_path(app_id)}/suggest-dependencies",
            )
            handle_response_error(resp)
            return SuggestDependenciesResponse.model_validate(resp.json())

    response = run_api_call(_suggest())

    if not response.suggestions:
        if json_mode:
            output({"suggestions": [], "applied": []}, json_mode=True)
        else:
            print_info(
                "No dependencies suggested. If you already know which flows "
                "gate which, declare them with `user-story update --depends-on`."
            )
        return

    # Pull every story for the app once so we can render names beside the
    # IDs in the prompt + confirmation flow. The API only returns ids.
    async def _stories() -> dict[str, dict[str, Any]]:
        async with ApiClient(settings) as client:
            return await _fetch_all_stories_inner(client, app_id)

    stories_by_id = run_api_call(_stories())

    def _label(sid: str) -> str:
        name = stories_by_id.get(sid, {}).get("name") or "<unknown>"
        return f"{name} ({sid[:8]})"

    if json_mode:
        # JSON mode skips the interactive flow entirely: --yes auto-applies,
        # otherwise we just emit the raw suggestions for piping. This matches
        # how the rest of the CLI treats --json (machine-readable, no TTY UI).
        if yes:
            applied = _apply_suggestions(settings, app_id, response.suggestions)
            output(
                {
                    "suggestions": [s.model_dump(by_alias=True) for s in response.suggestions],
                    "applied": [
                        {"userStoryId": cid, "dependsOn": parents}
                        for cid, parents in applied.items()
                    ],
                },
                json_mode=True,
            )
        else:
            output(
                {"suggestions": [s.model_dump(by_alias=True) for s in response.suggestions]},
                json_mode=True,
            )
        return

    rows = [
        [
            _label(s.user_story_id),
            _label(s.depends_on_user_story_id),
            f"{s.confidence:.2f}",
            s.reasoning,
        ]
        for s in response.suggestions
    ]
    print_table(
        ["Story", "Depends on", "Confidence", "Reasoning"],
        rows,
        title=f"Suggested dependencies ({len(response.suggestions)})",
    )

    # Non-TTY without --yes is ambiguous: typer.confirm would raise on a
    # missing stdin, so fail fast with a clear message instead.
    if not yes and not sys.stdin.isatty():
        print_error(
            "suggest-deps in a non-TTY context requires --yes (or pipe `yes` "
            "in). Skipping to avoid hanging on confirmation prompts."
        )
        raise typer.Exit(code=1)

    accepted = (
        list(response.suggestions)
        if yes
        else [
            s
            for s in response.suggestions
            if typer.confirm(
                f"Apply: {_label(s.user_story_id)} → {_label(s.depends_on_user_story_id)}?"
            )
        ]
    )
    if not accepted:
        print_info("No suggestions applied.")
        return

    applied = _apply_suggestions(settings, app_id, accepted)
    print_success(
        f"Applied {sum(len(p) for p in applied.values())} dependency edge(s) "
        f"across {len(applied)} user stor{'y' if len(applied) == 1 else 'ies'}."
    )


async def _fetch_all_stories_inner(client: ApiClient, app_id: str) -> dict[str, dict[str, Any]]:
    """Coroutine version of ``_fetch_all_stories`` for use inside an async block.

    Kept separate so the synchronous wrapper above can call it via
    ``run_api_call``; this one assumes the caller already awaits the client.
    """
    out: dict[str, dict[str, Any]] = {}
    page = 1
    while True:
        resp = await client.get(base_path(app_id), params={"page": page, "page_size": 100})
        handle_response_error(resp)
        body = resp.json()
        items = body.get("items", []) if isinstance(body, dict) else body
        for item in items:
            sid = item.get("id")
            if sid:
                out[sid] = item
        total = body.get("total") if isinstance(body, dict) else None
        if not items or (total is not None and len(out) >= total):
            break
        page += 1
    return out


def _apply_suggestions(
    settings: Any,
    app_id: str,
    accepted: list[Any],
) -> dict[str, list[str]]:
    """Group accepted suggestions by child and PATCH each child once.

    For each child we GET the current ``depends_on`` set and union with the
    accepted parents — a missing parent the user already wired up via the
    webapp survives this call, and the LLM's suggestion stays additive.
    Returns ``{child_id: [parent_id, ...]}`` describing the new full set
    sent to each PATCH (mostly for JSON-mode reporting).
    """
    by_child: dict[str, list[str]] = defaultdict(list)
    for s in accepted:
        by_child[s.user_story_id].append(s.depends_on_user_story_id)

    async def _run() -> dict[str, list[str]]:
        async with ApiClient(settings) as client:
            applied: dict[str, list[str]] = {}
            for child_id, new_parents in by_child.items():
                get_resp = await client.get(f"{base_path(app_id)}/{child_id}")
                handle_response_error(get_resp)
                current = get_resp.json()
                current_deps = current.get("dependsOn") or current.get("depends_on") or []
                merged = list({*current_deps, *new_parents})
                patch_resp = await client.patch(
                    f"{base_path(app_id)}/{child_id}",
                    json={"dependsOn": merged},
                )
                handle_response_error(patch_resp)
                applied[child_id] = merged
            return applied

    try:
        return run_api_call(_run())
    except typer.Exit:
        # 422 (cycle / cross-app) propagates as Exit from handle_response_error;
        # warn the user that some suggestions may have been applied before the
        # failure so they can re-run rather than wonder about partial state.
        print_warning(
            "One or more PATCHes failed (likely a cycle introduced by the LLM "
            "suggestions). Earlier accepted suggestions may have been applied; "
            "re-run `user-story suggest-deps` to see the current state."
        )
        raise


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
