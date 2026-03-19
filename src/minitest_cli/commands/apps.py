"""App management commands: list, show."""

import typer

app = typer.Typer(name="apps", help="App management.")


@app.command(name="list")
def list_apps() -> None:
    """List all apps."""
    typer.echo("apps list – not yet implemented", err=True)
    raise typer.Exit(code=1)


@app.command()
def show() -> None:
    """Show details for a specific app."""
    typer.echo("apps show – not yet implemented", err=True)
    raise typer.Exit(code=1)
