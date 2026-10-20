"""Build management commands: upload, list."""

from pathlib import Path
from typing import Annotated, Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.build_helpers import (
    BUILD_TABLE_HEADERS,
    BuildKindFilter,
    BuildStatusFilter,
    Platform,
    base_path,
    detect_platform,
    format_build_row,
    format_pagination_info,
    handle_response_error,
    print_validation_warnings,
    resolve_app,
    run_api_call,
    upload_status_message,
)
from minitest_cli.commands.build_commit import from_commit
from minitest_cli.commands.build_get import get
from minitest_cli.commands.build_fix_prompts import print_fix_prompts, redacted_payload
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
                "Path to the build file (.apk, .apks, .ipa or .app.zip). A Simulator build"
                " for iOS or an emulator-compatible Android build, unless --physical."
            ),
            exists=True,
            readable=True,
        ),
    ],
    platform: Annotated[
        Platform | None,
        typer.Option(help="Target platform. Auto-detected from file extension."),
    ] = None,
    physical: Annotated[
        bool,
        typer.Option(
            "--physical",
            help=(
                "Upload a build for physical devices: a signed iOS device .ipa (Ad Hoc or"
                " Development) or an Android .apk for real phones."
            ),
        ),
    ] = False,
) -> None:
    """Upload a build file (.apk or .apks for Android, .ipa or .app.zip for iOS).

    By default builds are checked for virtual devices:

    \b
    - iOS: provide a Simulator build (.ipa or .app.zip built for the iOS Simulator).
    - Android: provide an emulator-compatible .apk or .apks archive.

    With --physical, builds are checked for physical devices instead: an iOS
    device .ipa signed for Minitap's iPhones, or an Android .apk. Start runs on
    them with --ios-physical / --android-physical.
    """
    settings, app_id, json_mode = resolve_app()
    resolved_platform = platform.value if platform else detect_platform(file)
    form = {"platform": resolved_platform}
    if physical:
        form["backend"] = "physical"

    async def _run() -> BuildResponse:
        async with ApiClient(settings) as client:
            with (
                file.open("rb") as f,
                err_console.status(upload_status_message(file)),
            ):
                resp = await client.upload_file(
                    f"{base_path(app_id)}/build",
                    files={"file": (file.name, f, "application/octet-stream")},
                    data=form,
                )
        handle_response_error(resp, physical=physical)
        return BuildResponse.model_validate(resp.json())

    result = run_api_call(_run())
    result_dict = result.model_dump(mode="json", by_alias=True)

    if json_mode:
        output(result_dict, json_mode=True)
    else:
        print_validation_warnings(result.validation_warnings)
        devices = ", physical devices" if physical else ""
        print_success(f"Build uploaded: {file.name} ({resolved_platform}{devices})")
        output(result_dict, json_mode=False)


@app.command(name="list")
def list_builds(
    page: Annotated[int, typer.Option(help="Page number.")] = 1,
    page_size: Annotated[int, typer.Option(help="Results per page.")] = 20,
    platform: Annotated[
        Platform | None,
        typer.Option(help="Filter by platform."),
    ] = None,
    status: Annotated[
        list[BuildStatusFilter] | None,
        typer.Option(
            "--status", help="Filter by build status. Repeatable. Defaults to completed only."
        ),
    ] = None,
    kind: Annotated[BuildKindFilter | None, typer.Option(help="Filter by build kind.")] = None,
    all_pages: Annotated[bool, typer.Option("--all", help="Fetch all results.")] = False,
) -> None:
    """List builds for the active app."""
    settings, app_id, json_mode = resolve_app()
    platform_value = platform.value if platform else None

    if all_pages:
        page, page_size = 1, 100

    async def _run() -> BuildListResponse:
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        if platform_value is not None:
            params["platform"] = platform_value
        if kind is not None:
            params["kind"] = kind.value
        if status:
            params["status"] = [s.value for s in status]

        async with ApiClient(settings) as client:
            resp = await client.get(f"{base_path(app_id)}/builds", params=params)
        handle_response_error(resp)
        return BuildListResponse.model_validate(resp.json())

    result = run_api_call(_run())

    if json_mode:
        output(redacted_payload(result), json_mode=True)
        return

    if not result.items:
        print_info("No builds found.")
        return

    title, tip = format_pagination_info(result)
    rows = [format_build_row(b) for b in result.items]
    print_table(BUILD_TABLE_HEADERS, rows, title=title)
    if tip:
        print_info(tip)
    print_fix_prompts(result.items)


app.command(name="get")(get)
app.command(name="from-commit")(from_commit)
