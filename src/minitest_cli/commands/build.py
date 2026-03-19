"""Build management commands: list, upload."""

import typer

from minitest_cli.core.auth import require_auth
from minitest_cli.core.config import Settings

app = typer.Typer(name="build", help="Build management.")


def _get_settings() -> Settings:
    return typer.Context.settings  # type: ignore[attr-defined]


@app.command(name="list")
def list_builds() -> None:
    """List builds for the active app."""
    require_auth(_get_settings())
    typer.echo("build list – not yet implemented", err=True)
    raise typer.Exit(code=1)


@app.command()
def upload() -> None:
    """Upload a new build."""
    require_auth(_get_settings())
    typer.echo("build upload – not yet implemented", err=True)
    raise typer.Exit(code=1)
