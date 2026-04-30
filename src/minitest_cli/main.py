"""Minitest CLI – Typer application entry point."""

from typing import Annotated

import typer

from minitest_cli import __version__
from minitest_cli.commands import (
    app_knowledge,
    apps,
    auth,
    batch,
    build,
    flow_types,
    maintenance_check,
    run,
    skill,
    upgrade,
    user_story,
)
from minitest_cli.core.config import get_settings
from minitest_cli.utils.update_check import check_for_updates

app = typer.Typer(
    name="minitest",
    help="Minitest CLI – command-line interface for the Minitest testing platform.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

# Register command groups
app.add_typer(auth.app)
app.add_typer(apps.app)
app.add_typer(user_story.app)
app.add_typer(flow_types.app)
app.add_typer(app_knowledge.app)
app.add_typer(build.app)
app.add_typer(maintenance_check.app)
app.add_typer(run.app)
app.add_typer(batch.app)
app.add_typer(skill.app)
app.add_typer(upgrade.app)


def _version_callback(value: bool) -> None:
    if value:
        print(f"minitest-cli {__version__}")  # noqa: T201
        raise typer.Exit()


@app.callback()
def main(
    _version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-v",
            help="Show CLI version and exit.",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = False,
    json: Annotated[  # noqa: A002
        bool,
        typer.Option(
            "--json",
            help="Output JSON to stdout. Diagnostics go to stderr.",
        ),
    ] = False,
    app_id: Annotated[
        str | None,
        typer.Option(
            "--app",
            help="Target app ID or name. Overrides MINITEST_APP_ID.",
        ),
    ] = None,
) -> None:
    """Global options applied before any subcommand."""
    settings = get_settings()

    # Store global state in the Typer context
    ctx = typer.Context
    ctx.json_mode = json  # type: ignore[attr-defined]
    ctx.app_flag = app_id  # type: ignore[attr-defined]
    ctx.settings = settings  # type: ignore[attr-defined]

    # Non-blocking update check
    check_for_updates(settings)
