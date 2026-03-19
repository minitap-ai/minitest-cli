"""Test execution commands: start, status, list."""

import typer

from minitest_cli.core.auth import require_auth
from minitest_cli.core.config import Settings

app = typer.Typer(name="run", help="Test execution.")


def _get_settings() -> Settings:
    return typer.Context.settings  # type: ignore[attr-defined]


@app.command()
def start() -> None:
    """Start a new test run."""
    require_auth(_get_settings())
    typer.echo("run start – not yet implemented", err=True)
    raise typer.Exit(code=1)


@app.command()
def status() -> None:
    """Check the status of a test run."""
    require_auth(_get_settings())
    typer.echo("run status – not yet implemented", err=True)
    raise typer.Exit(code=1)


@app.command(name="list")
def list_runs() -> None:
    """List recent test runs."""
    require_auth(_get_settings())
    typer.echo("run list – not yet implemented", err=True)
    raise typer.Exit(code=1)
