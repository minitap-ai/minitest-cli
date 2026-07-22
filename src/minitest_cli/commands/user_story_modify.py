"""User-story modification commands: update, delete."""

from pathlib import Path
from typing import Annotated, Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.user_story_camera import (
    CAMERA_MEDIA_HELP,
    resolve_camera_media_file_id,
    resolve_camera_source,
)
from minitest_cli.commands.user_story_device_count import (
    DeviceCountUpdateOption,
    describe_device_count_change,
    parse_device_count,
)
from minitest_cli.commands.user_story_criteria import apply_current_story_fields
from minitest_cli.commands.user_story_helpers import (
    base_path,
    get_app_flag,
    get_settings,
    handle_response_error,
    is_json_mode,
    run_api_call,
    validate_user_story_type,
)
from minitest_cli.commands.user_story_profiles import format_bound_profiles
from minitest_cli.core.app_context import resolve_app_id
from minitest_cli.core.auth import require_auth
from minitest_cli.models.user_story import UpdateUserStoryRequest
from minitest_cli.utils.output import output, print_error, print_info, print_success, print_warning


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
    device_count: DeviceCountUpdateOption = None,
    camera_media: Annotated[
        str | None, typer.Option("--camera-media", help=CAMERA_MEDIA_HELP)
    ] = None,
    clear_camera_media: Annotated[
        bool,
        typer.Option(
            "--clear-camera-media",
            help="Reset the camera media to the default feed. Excludes --camera-media.",
        ),
    ] = False,
) -> None:
    """Update an existing user story (partial update)."""
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

    if camera_media is not None and clear_camera_media:
        print_error("Use either --camera-media or --clear-camera-media, not both.")
        raise typer.Exit(code=1)

    camera_source = resolve_camera_source(camera_media)

    if user_story_type is not None:
        validate_user_story_type(user_story_type, settings)

    device_count_provided = device_count is not None
    device_count_value = parse_device_count(device_count) if device_count_provided else None

    # --depends-on (replace) wins over --remove-dependency (delta); warn on the dropped removal.
    if depends_on is not None and remove_dependency:
        print_warning("--remove-dependency ignored when --depends-on is set.")

    # Criteria edits and dependency removals need the current story to preserve
    # criterion identity or subtract from the live dep set, so defer the payload.
    needs_current_story_criteria = criteria is not None or bool(add_criteria)
    needs_current_story_deps = depends_on is None and bool(remove_dependency)
    needs_current_story = needs_current_story_criteria or needs_current_story_deps

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
    has_camera_change = camera_source is not None or clear_camera_media
    has_any_change = (
        req.has_changes() or needs_current_story or device_count_provided or has_camera_change
    )
    if not has_any_change:
        print_error("Provide at least one field to update.")
        raise typer.Exit(code=1)

    payload = req.to_payload()
    if device_count_provided:
        payload["deviceCount"] = device_count_value
    # Explicit null clears server-side; to_payload's exclude_none would drop it.
    if clear_camera_media:
        payload["cameraMediaFileId"] = None
    elif isinstance(camera_source, str):
        payload["cameraMediaFileId"] = camera_source

    async def _run() -> dict[str, Any]:
        async with ApiClient(settings) as client:
            path = f"{base_path(app_id)}/{user_story_id}"
            if isinstance(camera_source, Path):
                payload["cameraMediaFileId"] = await resolve_camera_media_file_id(
                    client, app_id, camera_source
                )
            if needs_current_story:
                await apply_current_story_fields(
                    client,
                    path,
                    payload,
                    criteria=criteria,
                    add_criteria=add_criteria,
                    remove_dependency=remove_dependency,
                    subtract_deps=needs_current_story_deps,
                )
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
        if device_count_provided:
            print_info(describe_device_count_change(data, device_count_value))
        if clear_camera_media:
            print_info("Camera media reset to the built-in default feed.")
    output(data, json_mode=json_mode)
