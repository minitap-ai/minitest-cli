"""Build management commands: upload, list."""

from pathlib import Path
from typing import Annotated

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.build_helpers import (
    BUILD_TABLE_HEADERS,
    Platform,
    base_path,
    detect_platform,
    format_build_row,
    format_pagination_info,
    handle_response_error,
    resolve_app,
    run_api_call,
    upload_status_message,
)
from minitest_cli.models import BuildListResponse, BuildResponse
from minitest_cli.utils.output import (
    err_console,
    output,
    print_info,
    print_success,
    print_table,
)

app = typer.Typer(name="build", help="Build management.")


@app.command()
def upload(
    file: Annotated[
        Path,
        typer.Argument(
            help=(
                "Path to the build file (.apk or .ipa). Must be a Simulator"
                " build for iOS or an x86_64-compatible .apk for Android."
            ),
            exists=True,
            readable=True,
        ),
    ],
    platform: Annotated[
        Platform | None,
        typer.Option(help="Target platform. Auto-detected from file extension."),
    ] = None,
) -> None:
    """Upload a build file (.apk for Android, .ipa for iOS).

    Builds must be compatible with virtual devices:

    \b
    - iOS: provide a Simulator build (.ipa built for the iOS Simulator, not a physical device).
    - Android: provide an x86_64-compatible .apk (most emulator images are x86_64).
    """
    settings, app_id, json_mode = resolve_app()
    resolved_platform = platform.value if platform else detect_platform(file)

    async def _run() -> BuildResponse:
        async with ApiClient(settings) as client:
            with (
                file.open("rb") as f,
                err_console.status(upload_status_message(file)),
            ):
                resp = await client.upload_file(
                    f"{base_path(app_id)}/build",
                    files={"file": (file.name, f, "application/octet-stream")},
                    data={"platform": resolved_platform},
                )
        handle_response_error(resp)
        return BuildResponse.model_validate(resp.json())

    result = run_api_call(_run())
    result_dict = result.model_dump(mode="json")

    if json_mode:
        output(result_dict, json_mode=True)
    else:
        print_success(f"Build uploaded: {file.name} ({resolved_platform})")
        output(result_dict, json_mode=False)


@app.command(name="list")
def list_builds(
    page: Annotated[int, typer.Option(help="Page number.")] = 1,
    page_size: Annotated[int, typer.Option(help="Results per page.")] = 20,
    platform: Annotated[
        Platform | None,
        typer.Option(help="Filter by platform."),
    ] = None,
    all_pages: Annotated[bool, typer.Option("--all", help="Fetch all results.")] = False,
) -> None:
    """List builds for the active app."""
    settings, app_id, json_mode = resolve_app()
    platform_value = platform.value if platform else None

    if all_pages:
        page, page_size = 1, 100

    async def _run() -> BuildListResponse:
        params: dict[str, str | int] = {"page": page, "page_size": page_size}
        if platform_value is not None:
            params["platform"] = platform_value

        async with ApiClient(settings) as client:
            resp = await client.get(f"{base_path(app_id)}/builds", params=params)
        handle_response_error(resp)
        return BuildListResponse.model_validate(resp.json())

    result = run_api_call(_run())

    if json_mode:
        output(result.model_dump(mode="json"), json_mode=True)
        return

    if not result.items:
        print_info("No builds found.")
        return

    title, tip = format_pagination_info(result)
    rows = [format_build_row(b) for b in result.items]
    print_table(BUILD_TABLE_HEADERS, rows, title=title)
    if tip:
        print_info(tip)
