"""Wait for an uploaded .aab to be converted into the APK(s) its build installs."""

import asyncio
import time

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands._response_errors import EXIT_BUILD_INVALID
from minitest_cli.commands.build_helpers import base_path, handle_response_error
from minitest_cli.models import BuildResponse
from minitest_cli.utils.output import print_error

CONVERSION_POLL_SECONDS = 5.0
CONVERSION_TIMEOUT_SECONDS = 20 * 60


async def wait_for_conversion(
    client: ApiClient, app_id: str, build: BuildResponse
) -> BuildResponse:
    """Poll the build until it leaves ``pending``; exit when it fails or never finishes."""
    deadline = time.monotonic() + CONVERSION_TIMEOUT_SECONDS
    while build.status == "pending":
        if time.monotonic() > deadline:
            print_error(
                f"Build {build.id} is still being converted. "
                f"Check it later with `minitest build get {build.id}`."
            )
            raise typer.Exit(code=1)
        await asyncio.sleep(CONVERSION_POLL_SECONDS)
        resp = await client.get(f"{base_path(app_id)}/builds/{build.id}")
        handle_response_error(resp, resource="Build")
        build = BuildResponse.model_validate(resp.json())
    if build.status == "failed":
        print_error(f"The .aab could not be converted: {build.error_summary or 'unknown error'}")
        if build.error_remediation:
            print_error(build.error_remediation)
        raise typer.Exit(code=EXIT_BUILD_INVALID)
    return build
