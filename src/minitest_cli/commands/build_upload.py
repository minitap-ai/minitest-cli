"""Upload one build file, shared by `minitest build upload` and `minitest pr check`."""

from pathlib import Path

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.build_bundle import PHYSICAL_AAB_NOTE
from minitest_cli.commands.build_conversion import wait_for_conversion
from minitest_cli.commands.build_helpers import (
    base_path,
    handle_response_error,
    upload_status_message,
)
from minitest_cli.models import BuildResponse
from minitest_cli.utils.output import err_console, print_info


async def upload_build(
    client: ApiClient,
    app_id: str,
    file: Path,
    platform: str,
    *,
    physical: bool = False,
    wait: bool = True,
) -> BuildResponse:
    is_bundle = file.suffix.lower() == ".aab"
    form = {"platform": platform}
    if physical:
        # Still sent for an .aab: older backends use it to pick the bundle's ABI.
        form["backend"] = "physical"
        if is_bundle:
            print_info(PHYSICAL_AAB_NOTE)
    with file.open("rb") as f, err_console.status(upload_status_message(file)):
        resp = await client.upload_file(
            f"{base_path(app_id)}/build",
            files={"file": (file.name, f, "application/octet-stream")},
            data=form,
        )
    handle_response_error(resp, physical=physical)
    build = BuildResponse.model_validate(resp.json())
    if wait and is_bundle:
        with err_console.status("Converting the .aab into APKs..."):
            build = await wait_for_conversion(client, app_id, build)
    return build
