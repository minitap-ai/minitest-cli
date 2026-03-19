"""App management commands: list, show."""

import typer

from minitest_cli.core.auth import require_auth
from minitest_cli.core.config import Settings

app = typer.Typer(name="apps", help="App management.")


def _get_settings() -> Settings:
    return typer.Context.settings  # type: ignore[attr-defined]


@app.command(name="list")
def list_apps() -> None:
    """List all apps."""
    require_auth(_get_settings())
    typer.echo("apps list – not yet implemented", err=True)
    raise typer.Exit(code=1)


@app.command()
def show() -> None:
    """Show details for a specific app."""
    require_auth(_get_settings())
    typer.echo("apps show – not yet implemented", err=True)
    raise typer.Exit(code=1)
