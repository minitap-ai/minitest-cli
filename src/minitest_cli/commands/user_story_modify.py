"""User-story modification commands: update, delete."""

from typing import Annotated

import typer

from minitest_cli.commands.user_story_camera import (
    CAMERA_MEDIA_HELP,
    resolve_camera_source,
)
from minitest_cli.commands.user_story_device_count import (
    DeviceCountUpdateOption,
    parse_device_count,
)
from minitest_cli.commands.user_story_helpers import (
    get_app_flag,
    get_settings,
    is_json_mode,
    run_api_call,
    validate_user_story_type,
)
from minitest_cli.commands.user_story_overrides import (
    guard_conflicting_flags,
    parse_clear_override,
    parse_set_override,
)
from minitest_cli.commands.user_story_update import (
    build_update_payload,
    patch_user_story,
    print_update_summary,
)
from minitest_cli.core.app_context import resolve_app_id
from minitest_cli.core.auth import require_auth
from minitest_cli.utils.output import output, print_warning


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
    override: Annotated[
        list[str] | None,
        typer.Option(
            "--override",
            help="Set a criterion's override: <platform>:<id-or-index>:<text> (repeatable).",
        ),
    ] = None,
    clear_override: Annotated[
        list[str] | None,
        typer.Option(
            "--clear-override",
            help="Clear a criterion's override: <platform>:<id-or-index> (repeatable).",
        ),
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

    set_overrides = [parse_set_override(v) for v in (override or [])]
    clear_overrides = [parse_clear_override(v) for v in (clear_override or [])]
    guard_conflicting_flags(
        criteria=criteria,
        add_criteria=add_criteria,
        profile=profile,
        clear_profiles=clear_profiles,
        camera_media=camera_media,
        clear_camera_media=clear_camera_media,
        has_overrides=bool(set_overrides or clear_overrides),
    )

    camera_source = resolve_camera_source(camera_media)

    if user_story_type is not None:
        validate_user_story_type(user_story_type, settings)

    device_count_provided = device_count is not None
    device_count_value = parse_device_count(device_count) if device_count_provided else None

    if depends_on is not None and remove_dependency:
        print_warning("--remove-dependency ignored when --depends-on is set.")

    # Criteria/override/dependency edits defer the payload until the live story is read.
    needs_current_story_deps = depends_on is None and bool(remove_dependency)
    needs_current_story = bool(
        criteria is not None
        or add_criteria
        or needs_current_story_deps
        or set_overrides
        or clear_overrides
    )

    payload = build_update_payload(
        name=name,
        user_story_type=user_story_type,
        description=description,
        depends_on=depends_on,
        profile=profile,
        clear_profiles=clear_profiles,
        device_count_provided=device_count_provided,
        device_count_value=device_count_value,
        camera_source=camera_source,
        clear_camera_media=clear_camera_media,
        needs_current_story=needs_current_story,
    )

    data = run_api_call(
        patch_user_story(
            settings,
            app_id,
            user_story_id,
            payload,
            camera_source=camera_source,
            needs_current_story=needs_current_story,
            criteria=criteria,
            add_criteria=add_criteria,
            remove_dependency=remove_dependency,
            subtract_deps=needs_current_story_deps,
            set_overrides=set_overrides,
            clear_overrides=clear_overrides,
        )
    )
    if not json_mode:
        print_update_summary(
            data,
            user_story_id=user_story_id,
            clear_profiles=clear_profiles,
            profile=profile,
            device_count_provided=device_count_provided,
            device_count_value=device_count_value,
            clear_camera_media=clear_camera_media,
        )
    output(data, json_mode=json_mode)
