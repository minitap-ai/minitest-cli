"""Readable answers to the batch and schedule refusals about targets."""

import httpx
import typer

from minitest_cli.commands._response_errors import EXIT_NETWORK_ERROR, extract_detail
from minitest_cli.utils.output import err_console, print_error

CATALOG_HINT = "list what the workspace can ask for with `minitest targets catalog`."

# (marker in the server detail, what to tell the user, how to fix it)
_REFUSALS: tuple[tuple[str, str, str], ...] = (
    (
        "may appear at most once per batch",
        "Several devices per platform are not enabled for this workspace.",
        "keep one --target per mobile platform and one per browser, or ask Minitap to"
        " enable several devices per platform.",
    ),
    (
        "Several native targets on",
        "Several devices per platform are not enabled for this workspace.",
        "keep one --target per mobile platform, or ask Minitap to enable several devices"
        " per platform.",
    ),
    (
        "browser_version_requested is not available for this workspace",
        "Browser versions are not enabled for this workspace.",
        "drop version= from the web targets to run each browser's default version.",
    ),
    (
        "Android TV testing is not enabled",
        "Android TV is not enabled for this workspace.",
        "ask Minitap to enable Android TV testing.",
    ),
    (
        "Native tablet testing is not enabled",
        "Tablets are not enabled for this workspace.",
        "drop device=tablet (or --*-device-type tablet), or ask Minitap to enable tablets.",
    ),
    (
        "cannot mix a physical and a cloud iOS target",
        "One commit run cannot test iOS on both simulators and physical iPhones.",
        "start two runs, one per kind of iOS device.",
    ),
    (
        "per-run target/URL overrides are available only",
        "This server does not accept per-run browsers from the CLI yet.",
        "drop the platform=web targets and pass --web to run the app's default web targets.",
    ),
    ("is not offered", "", CATALOG_HINT),
    ("A TV app runs only on Android TV", "", "drop device= and backend= on a TV app."),
)


def explain_target_refusal(resp: httpx.Response) -> None:
    """Exit with a readable message when ``resp`` refuses the run's targets."""
    if resp.status_code not in (403, 409, 422):
        return
    detail = extract_detail(resp)
    for marker, message, fix in _REFUSALS:
        if marker in detail:
            print_error(message or detail)
            if message:
                err_console.print(f"  [dim]Server said:[/dim] {detail}")
            err_console.print(f"  [yellow]Fix:[/yellow] {fix}")
            raise typer.Exit(code=EXIT_NETWORK_ERROR)
    if resp.status_code == 409:
        print_error(f"The run was refused: {detail}")
        raise typer.Exit(code=EXIT_NETWORK_ERROR)
