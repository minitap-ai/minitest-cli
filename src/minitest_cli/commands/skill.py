"""Skill command – fetch the latest CLI skill instructions from GitHub."""

import sys

import httpx
import typer

from minitest_cli.utils.output import err_console, print_error

app = typer.Typer(name="skill", help="Retrieve the minitest CLI skill for AI agents.")

SKILL_URL = (
    "https://raw.githubusercontent.com/minitap-ai/agent-skills/main/skills/minitest-cli/SKILL.md"
)

EXIT_NETWORK_ERROR = 3


@app.callback(invoke_without_command=True)
def skill(
    ctx: typer.Context,
) -> None:
    """Fetch and print the latest minitest CLI skill from GitHub.

    Outputs the SKILL.md content to stdout so AI agents can consume it.
    Diagnostics go to stderr.
    """
    if ctx.invoked_subcommand is not None:
        return

    err_console.print("[dim]Fetching latest skill from GitHub…[/dim]")

    try:
        resp = httpx.get(SKILL_URL, timeout=15, follow_redirects=True)
    except httpx.HTTPError as exc:
        print_error(f"Network error fetching skill: {exc}")
        raise typer.Exit(EXIT_NETWORK_ERROR) from exc

    if resp.status_code != 200:
        print_error(f"Failed to fetch skill: HTTP {resp.status_code}")
        raise typer.Exit(EXIT_NETWORK_ERROR)

    sys.stdout.write(resp.text)
