"""User-story modification commands: update, delete."""

from typing import Annotated, Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.user_story_helpers import (
    base_path,
    extract_criteria_items,
    get_app_flag,
    get_settings,
    handle_response_error,
    is_json_mode,
    run_api_call,
    validate_user_story_type,
)
from minitest_cli.commands.user_story_criteria import build_criteria_payload
from minitest_cli.commands.user_story_profiles import format_bound_profiles
from minitest_cli.core.app_context import resolve_app_id
from minitest_cli.core.auth import require_auth
from minitest_cli.models.user_story import UpdateUserStoryRequest
from minitest_cli.utils.output import (
    output,
    print_error,
    print_info,
    print_success,
    print_warning,
)


def update_user_story(
    user_story_id: Annotated[str, typer.Argument(help="User-story ID.")],
    name: Annotated[str | None, typer.Option("--name", help="New user-story name.")] = None,
    user_story_type: Annotated[
        str | None, typer.Option("--type", help="New user-story type.")
    ] = None,
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
    depends_on: Annotated[
        list[str] | None,
        typer.Option(
            "--depends-on",
            help=(
                "Replace the full set of parent user-story IDs (repeatable). "
                "Pass each parent ID once. Validated server-side: same-app, "
                "no cycles, no self-loops, references must exist."
            ),
        ),
    ] = None,
    remove_dependency: Annotated[
        list[str] | None,
        typer.Option(
            "--remove-dependency",
            help=(
                "Remove specific parent user-story IDs from the existing set "
                "(repeatable). Ignored when --depends-on is also provided."
            ),
        ),
    ] = None,
    profile: Annotated[
        list[str] | None,
        typer.Option(
            "--profile",
            help="Replace bound test profiles with these IDs (repeatable). Omit to leave as-is.",
        ),
    ] = None,
    clear_profiles: Annotated[
        bool,
        typer.Option(
            "--clear-profiles",
            help="Unbind all test profiles. Mutually exclusive with --profile.",
        ),
    ] = False,
) -> None:
    """Update an existing user story (partial update).

    Pass ``--depends-on`` to declare which flows gate this one. The
    server validates the graph (same-app, no cycles, references exist).
    """
    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)
    app_id = resolve_app_id(settings, get_app_flag())

    if criteria is not None and add_criteria is not None:
        print_error("Use either --criteria or --add-criteria, not both.")
        raise typer.Exit(code=1)

    if profile and clear_profiles:
        print_error("Use either --profile or --clear-profiles, not both.")
        raise typer.Exit(code=1)

    if user_story_type is not None:
        validate_user_story_type(user_story_type, settings)

    # ``--depends-on`` is the replace path; ``--remove-dependency`` is a delta
    # against the current set. If both are given, the spec says replace wins —
    # warn loudly so the user notices the surgical removal was dropped.
    if depends_on is not None and remove_dependency:
        print_warning("--remove-dependency ignored when --depends-on is set.")

    # When --criteria (full replace), --add-criteria (append), or
    # --remove-dependency (delta against the current set) is used we need the
    # current story so we can either preserve stable criterion identity or
    # subtract from the live dep set. We defer building the final payload
    # until after that GET.
    needs_current_story_criteria = criteria is not None or bool(add_criteria)
    needs_current_story_deps = depends_on is None and bool(remove_dependency)
    needs_current_story = needs_current_story_criteria or needs_current_story_deps

    # ``[]`` clears bindings, a list replaces them, ``None`` leaves them untouched.
    if clear_profiles:
        test_profile_ids: list[str] | None = []
    elif profile:
        test_profile_ids = list(profile)
    else:
        test_profile_ids = None

    req = UpdateUserStoryRequest(
        name=name,
        type=user_story_type,
        description=description,
        acceptance_criteria=None,
        depends_on=list(depends_on) if depends_on is not None else None,
        test_profile_ids=test_profile_ids,
    )
    if not req.has_changes() and not needs_current_story:
        print_error("Provide at least one field to update.")
        raise typer.Exit(code=1)

    payload = req.to_payload()

    async def _run() -> dict[str, Any]:
        async with ApiClient(settings) as client:
            path = f"{base_path(app_id)}/{user_story_id}"
            if needs_current_story:
                get_resp = await client.get(path)
                handle_response_error(get_resp)
                current_story = get_resp.json()
                if needs_current_story_criteria:
                    existing_items = extract_criteria_items(current_story)
                    payload["acceptanceCriteria"] = build_criteria_payload(
                        existing_items,
                        replace=list(criteria) if criteria is not None else None,
                        add=list(add_criteria) if add_criteria else None,
                    )
                if needs_current_story_deps:
                    current_deps = (
                        current_story.get("dependsOn") or current_story.get("depends_on") or []
                    )
                    to_remove = set(remove_dependency or [])
                    payload["dependsOn"] = [d for d in current_deps if d not in to_remove]
            resp = await client.patch(path, json=payload)
            handle_response_error(resp)
            return resp.json()

    data = run_api_call(_run())
    if not json_mode:
        print_success(f"User story updated: {user_story_id}")
        if clear_profiles:
            print_info("Test profiles cleared.")
        elif profile:
            print_info(f"Bound profiles: {format_bound_profiles(data) or ', '.join(profile)}")
    output(data, json_mode=json_mode)


def delete_user_story(
    user_story_id: Annotated[str, typer.Argument(help="User-story ID.")],
    force: Annotated[bool, typer.Option("--force", help="Skip confirmation.")] = False,
) -> None:
    """Delete a user story. Requires --force flag."""
    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)
    if not force:
        print_error("Delete requires --force flag.")
        raise typer.Exit(code=1)
    app_id = resolve_app_id(settings, get_app_flag())

    async def _run() -> None:
        async with ApiClient(settings) as client:
            resp = await client.delete(f"{base_path(app_id)}/{user_story_id}")
            handle_response_error(resp)

    run_api_call(_run())
    if json_mode:
        output({"deleted": True, "id": user_story_id}, json_mode=True)
    else:
        print_success(f"User story deleted: {user_story_id}")
