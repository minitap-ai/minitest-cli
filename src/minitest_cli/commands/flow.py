"""Testing flow commands: list, show, create."""

import typer

app = typer.Typer(name="flow", help="Testing flow operations.")


@app.command(name="list")
def list_flows() -> None:
    """List testing flows for the active app."""
    typer.echo("flow list – not yet implemented", err=True)
    raise typer.Exit(code=1)


@app.command()
def show() -> None:
    """Show details for a specific testing flow."""
    typer.echo("flow show – not yet implemented", err=True)
    raise typer.Exit(code=1)


@app.command()
def create() -> None:
    """Create a new testing flow."""
    typer.echo("flow create – not yet implemented", err=True)
    raise typer.Exit(code=1)
