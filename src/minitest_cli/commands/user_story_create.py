"""User-story create command."""

from pathlib import Path
from typing import Annotated, Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.user_story_camera import (
    CAMERA_MEDIA_HELP,
    resolve_camera_media_file_id,
    resolve_camera_source,
)
from minitest_cli.commands.user_story_device_count import DeviceCountCreateOption
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
from minitest_cli.utils.output import output, print_error, print_info, print_success


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
    profile: Annotated[
        list[str] | None,
        typer.Option(
            "--profile",
            help="Test profile ID to bind (repeatable). Omit to use the server's default profile.",
        ),
    ] = None,
    device_count: DeviceCountCreateOption = None,
    camera_media: Annotated[
        str | None, typer.Option("--camera-media", help=CAMERA_MEDIA_HELP)
    ] = None,
) -> None:
    """Create a new user story."""
    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)
    app_id = resolve_app_id(settings, get_app_flag())
    validate_user_story_type(user_story_type, settings)
    camera_source = resolve_camera_source(camera_media)
    payload: dict[str, Any] = {"name": name, "type": user_story_type}
    if description is not None:
        payload["description"] = description
    if criteria:
        payload["acceptance_criteria"] = list(criteria)
    if profile:
        payload["test_profile_ids"] = list(profile)
    if device_count is not None:
        payload["deviceCount"] = device_count
    if isinstance(camera_source, str):
        payload["camera_media_file_id"] = camera_source

    async def _run() -> dict[str, Any]:
        async with ApiClient(settings) as client:
            if isinstance(camera_source, Path):
                payload["camera_media_file_id"] = await resolve_camera_media_file_id(
                    client, app_id, camera_source
                )
            resp = await client.post(base_path(app_id), json=payload)
            handle_response_error(resp)
            created = resp.json()
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
        bound = format_bound_profiles(data)
        if bound:
            label = "Default profile auto-assigned" if not profile else "Profiles bound"
            print_info(f"{label}: {bound}")
    output(data, json_mode=json_mode)
