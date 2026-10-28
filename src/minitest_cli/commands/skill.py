import os
import sys

import httpx
import typer

from minitest_cli.api.errors import format_network_error
from minitest_cli.utils import skill_bundle
from minitest_cli.utils.output import err_console, print_error

app = typer.Typer(
    name="skill",
    help="Print the minitest CLI skill for your AI coding agent (not app skills: see app-skill).",
)

# Set to read the skill from somewhere else (a fork, a branch) instead of this install.
SKILL_URL_ENV = "MINITEST_SKILL_URL"

EXIT_NETWORK_ERROR = 3


@app.callback(invoke_without_command=True)
def skill(
    ctx: typer.Context,
) -> None:
    """Print the minitest CLI skill that matches this CLI version.

    Outputs the SKILL.md content to stdout so AI agents can consume it. The skill ships
    inside the CLI, so it works offline and always describes the installed commands.
    Diagnostics go to stderr.
    """
    if ctx.invoked_subcommand is not None:
        return

    url = os.environ.get(SKILL_URL_ENV)
    if url is None:
        sys.stdout.write(skill_bundle.bundled_skill_md())
        return

    err_console.print(f"[dim]Fetching skill from {url}…[/dim]")
    try:
        resp = httpx.get(url, timeout=15, follow_redirects=True)
    except httpx.HTTPError as exc:
        print_error(format_network_error(exc, action="fetching skill"))
        raise typer.Exit(EXIT_NETWORK_ERROR) from exc

    if resp.status_code != 200:
        print_error(f"Failed to fetch skill: HTTP {resp.status_code}")
        raise typer.Exit(EXIT_NETWORK_ERROR)

    sys.stdout.write(resp.text)
