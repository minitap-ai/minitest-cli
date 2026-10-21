"""Wait for an uploaded .aab to be converted into the APK(s) its builds install.

An .aab with asset packs converts into two builds sharing a bundle group: the
head (x86_64, for cloud emulators; the id the upload returns) and a phone
member (arm64, for physical devices). The head's ``variants`` lists both, so
polling the head is enough to follow every member. Older backends send no
``variants``: the head is then the only build to wait for.
"""

import asyncio
import time

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands._response_errors import EXIT_BUILD_INVALID
from minitest_cli.commands.build_helpers import base_path, handle_response_error
from minitest_cli.models import BuildResponse, BuildVariant
from minitest_cli.utils.output import print_error, print_warning

CONVERSION_POLL_SECONDS = 5.0
CONVERSION_TIMEOUT_SECONDS = 20 * 60


def variant_label(variant: BuildVariant) -> str:
    """Phone for the arm64 member; All devices when a member also runs on phones."""
    if variant.device_build:
        return "Phone"
    if "physical" in (variant.supported_backends or []):
        return "All devices"
    return "Emulator"


def _pending_ids(build: BuildResponse) -> list[str]:
    pending = [build.id] if build.status == "pending" else []
    pending += [v.id for v in build.variants or [] if v.status == "pending" and v.id != build.id]
    return pending


def _failed_members(build: BuildResponse) -> list[tuple[str, str | None]]:
    """``(label, error)`` of every failed member, the head included when it isn't a variant."""
    variants = build.variants or []
    failed = [
        (f"{variant_label(v)} build {v.id}", v.error_summary)
        for v in variants
        if v.status == "failed"
    ]
    if build.status == "failed" and all(v.id != build.id for v in variants):
        failed.insert(0, (f"Build {build.id}", build.error_summary))
    return failed


async def wait_for_conversion(
    client: ApiClient, app_id: str, build: BuildResponse
) -> BuildResponse:
    """Poll the head until it and every bundle member leave ``pending``.

    Succeeds when at least one member completed (warning about the failed
    ones); exits with the build-invalid code when none did and one failed.
    """
    deadline = time.monotonic() + CONVERSION_TIMEOUT_SECONDS
    while pending := _pending_ids(build):
        if time.monotonic() > deadline:
            print_error(
                f"Still being converted: {', '.join(pending)}. "
                f"Check it later with `minitest build get {build.id}`."
            )
            raise typer.Exit(code=1)
        await asyncio.sleep(CONVERSION_POLL_SECONDS)
        resp = await client.get(f"{base_path(app_id)}/builds/{build.id}")
        handle_response_error(resp, resource="Build")
        build = BuildResponse.model_validate(resp.json())

    statuses = [build.status, *(v.status for v in build.variants or [])]
    failed = _failed_members(build)
    if "completed" in statuses:
        for label, error in failed:
            print_warning(f"{label} could not be converted: {error or 'unknown error'}")
        return build
    if failed:
        reason = build.error_summary or failed[0][1] or "unknown error"
        print_error(f"The .aab could not be converted: {reason}")
        for label, error in failed if build.variants else []:
            print_error(f"{label}: {error or 'unknown error'}")
        if build.error_remediation:
            print_error(build.error_remediation)
        raise typer.Exit(code=EXIT_BUILD_INVALID)
    return build
