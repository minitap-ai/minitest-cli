"""``minitest build get``: read one build of the active app by id."""

from typing import Annotated

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.build_fix_prompts import print_fix_prompts, redacted_build
from minitest_cli.commands.build_helpers import (
    BUILD_TABLE_HEADERS,
    base_path,
    format_build_row,
    handle_response_error,
    resolve_app,
    run_api_call,
)
from minitest_cli.commands.run_helpers import ensure_uuid
from minitest_cli.models import BuildResponse
from minitest_cli.utils.output import output, print_table


def _version_label(build: BuildResponse) -> str | None:
    if build.app_version and build.build_number:
        return f"{build.app_version} ({build.build_number})"
    return build.app_version or build.build_number


def get(
    build_id: Annotated[str, typer.Argument(help="Build ID (from `minitest build list`).")],
) -> None:
    """Show one build of the active app: status, version, commit and failure guidance."""
    ensure_uuid(build_id, kind="build ID")
    settings, app_id, json_mode = resolve_app()

    async def _run() -> BuildResponse:
        async with ApiClient(settings) as client:
            resp = await client.get(f"{base_path(app_id)}/builds/{build_id}")
        handle_response_error(resp, resource="Build")
        return BuildResponse.model_validate(resp.json())

    build = run_api_call(_run())

    if json_mode:
        output(redacted_build(build), json_mode=True)
        return

    version = _version_label(build)
    title = f"Build {version}" if version else "Build"
    print_table(BUILD_TABLE_HEADERS, [format_build_row(build)], title=title)
    print_fix_prompts([build])
