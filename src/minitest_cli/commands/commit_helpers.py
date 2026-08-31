"""Shared pieces of the commit-driven build and run commands."""

import re
from typing import Annotated

import httpx
import typer

from minitest_cli.api.apps_manager_client import AppsManagerClient
from minitest_cli.commands._response_errors import extract_detail
from minitest_cli.core.config import Settings
from minitest_cli.models.commit_build import TriggerBuildResponse
from minitest_cli.utils.output import err_console, print_error

EXIT_GENERAL_ERROR = 1
EXIT_NETWORK_ERROR = 3

COMMIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
TRIGGER_TIMEOUT_SECONDS = 120.0
VALID_PLATFORMS = ("ios", "android", "web")

NO_REPO_MARKER = "no source repository"
PLATFORM_MISMATCH_MARKER = "are not enabled for this app"
CONNECT_REPO_HINT = "Connect a GitHub repository to this app in the Minitest web app, then retry."
PLATFORM_HINT = "Pass --platform explicitly, for example --platform web on a web app."

CommitShaArg = Annotated[
    str | None,
    typer.Argument(
        metavar="[SHA]",
        help="Full 40-character commit SHA. Omit to build the head of the default branch.",
    ),
]

PlatformOpt = Annotated[
    list[str] | None,
    typer.Option(
        "--platform",
        "-p",
        help=(
            "Platform to target (ios, android, web). Repeatable. "
            "Omitted means ios and android, so web apps must pass --platform web."
        ),
    ),
]


def validate_commit_sha(commit_sha: str | None) -> str | None:
    if commit_sha is None:
        return None
    if not COMMIT_SHA_PATTERN.fullmatch(commit_sha):
        print_error(
            f"Invalid commit SHA {commit_sha!r}: expected 40 lowercase hexadecimal characters."
        )
        raise typer.Exit(code=EXIT_GENERAL_ERROR)
    return commit_sha


def validate_platforms(platforms: list[str] | None) -> list[str] | None:
    if not platforms:
        return None
    unknown = sorted({p for p in platforms if p not in VALID_PLATFORMS})
    if unknown:
        print_error(f"Unknown platform(s) {unknown}. Expected one of {list(VALID_PLATFORMS)}.")
        raise typer.Exit(code=EXIT_GENERAL_ERROR)
    return list(dict.fromkeys(platforms))


def trigger_path(tenant_id: str, app_id: str) -> str:
    return f"/api/v1/tenants/{tenant_id}/apps/{app_id}/builds/trigger"


def raise_for_trigger_error(resp: httpx.Response) -> None:
    if resp.status_code < 400:
        return
    detail = extract_detail(resp)
    if NO_REPO_MARKER in detail.lower():
        print_error(f"No GitHub repository is connected to this app: {detail}")
        err_console.print(f"  [yellow]Fix:[/yellow] {CONNECT_REPO_HINT}")
        raise typer.Exit(code=EXIT_GENERAL_ERROR)
    print_error(f"Build trigger failed ({resp.status_code}): {detail}")
    if PLATFORM_MISMATCH_MARKER in detail:
        err_console.print(f"  [yellow]Fix:[/yellow] {PLATFORM_HINT}")
    raise typer.Exit(code=EXIT_NETWORK_ERROR)


async def trigger_commit_build(
    settings: Settings,
    *,
    tenant_id: str,
    app_id: str,
    commit_sha: str | None,
    platforms: list[str] | None,
    force_full_build: bool,
) -> TriggerBuildResponse:
    body: dict[str, object] = {"forceFullBuild": force_full_build}
    if commit_sha:
        body["commitSha"] = commit_sha
    if platforms:
        body["platforms"] = platforms

    async with AppsManagerClient(settings) as client:
        resp = await client.post(
            trigger_path(tenant_id, app_id), json=body, timeout=TRIGGER_TIMEOUT_SECONDS
        )
    raise_for_trigger_error(resp)
    return TriggerBuildResponse.model_validate(resp.json())
