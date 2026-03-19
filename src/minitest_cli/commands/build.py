"""Build management commands: list, upload."""

import typer

app = typer.Typer(name="build", help="Build management.")


@app.command(name="list")
def list_builds() -> None:
    """List builds for the active app."""
    typer.echo("build list – not yet implemented", err=True)
    raise typer.Exit(code=1)


@app.command()
def upload() -> None:
    """Upload a new build."""
    typer.echo("build upload – not yet implemented", err=True)
    raise typer.Exit(code=1)
