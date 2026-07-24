"""Orchestration helpers for the ``user-story update`` command."""

from pathlib import Path
from typing import Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.user_story_camera import resolve_camera_media_file_id
from minitest_cli.commands.user_story_criteria import apply_current_story_fields
from minitest_cli.commands.user_story_device_count import describe_device_count_change
from minitest_cli.commands.user_story_helpers import base_path, handle_response_error
from minitest_cli.commands.user_story_overrides import ClearOverride, SetOverride
from minitest_cli.commands.user_story_profiles import format_bound_profiles
from minitest_cli.core.config import Settings
from minitest_cli.models.user_story import UpdateUserStoryRequest
from minitest_cli.utils.output import print_error, print_info, print_success


def build_update_payload(
    *,
    name: str | None,
    user_story_type: str | None,
    description: str | None,
    depends_on: list[str] | None,
    profile: list[str] | None,
    clear_profiles: bool,
    device_count_provided: bool,
    device_count_value: int | None,
    camera_source: Path | str | None,
    clear_camera_media: bool,
    needs_current_story: bool,
) -> dict[str, Any]:
    """Assemble the PATCH body from scalar edits, erroring if nothing would change."""
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
    if not (req.has_changes() or needs_current_story or device_count_provided or has_camera_change):
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
    return payload


async def patch_user_story(
    settings: Settings,
    app_id: str,
    user_story_id: str,
    payload: dict[str, Any],
    *,
    camera_source: Path | str | None,
    needs_current_story: bool,
    criteria: list[str] | None,
    add_criteria: list[str] | None,
    remove_dependency: list[str] | None,
    subtract_deps: bool,
    set_overrides: list[SetOverride],
    clear_overrides: list[ClearOverride],
) -> dict[str, Any]:
    """Resolve deferred fields against the live story, then PATCH the update."""
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
                subtract_deps=subtract_deps,
                set_overrides=set_overrides,
                clear_overrides=clear_overrides,
            )
        resp = await client.patch(path, json=payload)
        handle_response_error(resp)
        return resp.json()


def print_update_summary(
    data: dict[str, Any],
    *,
    user_story_id: str,
    clear_profiles: bool,
    profile: list[str] | None,
    device_count_provided: bool,
    device_count_value: int | None,
    clear_camera_media: bool,
) -> None:
    print_success(f"User story updated: {user_story_id}")
    if clear_profiles:
        print_info("Test profiles cleared.")
    elif profile:
        print_info(f"Bound profiles: {format_bound_profiles(data) or ', '.join(profile)}")
    if device_count_provided:
        print_info(describe_device_count_change(data, device_count_value))
    if clear_camera_media:
        print_info("Camera media reset to the built-in default feed.")
