"""Testing flow commands: list, show, create."""

import typer

from minitest_cli.core.auth import require_auth
from minitest_cli.core.config import Settings

app = typer.Typer(name="flow", help="Testing flow operations.")


def _get_settings() -> Settings:
    return typer.Context.settings  # type: ignore[attr-defined]


@app.command(name="list")
def list_flows() -> None:
    """List testing flows for the active app."""
    require_auth(_get_settings())
    typer.echo("flow list – not yet implemented", err=True)
    raise typer.Exit(code=1)


@app.command()
def show() -> None:
    """Show details for a specific testing flow."""
    require_auth(_get_settings())
    typer.echo("flow show – not yet implemented", err=True)
    raise typer.Exit(code=1)


@app.command()
def create() -> None:
    """Create a new testing flow."""
    require_auth(_get_settings())
    typer.echo("flow create – not yet implemented", err=True)
    raise typer.Exit(code=1)
