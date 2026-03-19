"""Test execution commands: start, status, list."""

import typer

app = typer.Typer(name="run", help="Test execution.")


@app.command()
def start() -> None:
    """Start a new test run."""
    typer.echo("run start – not yet implemented", err=True)
    raise typer.Exit(code=1)


@app.command()
def status() -> None:
    """Check the status of a test run."""
    typer.echo("run status – not yet implemented", err=True)
    raise typer.Exit(code=1)


@app.command(name="list")
def list_runs() -> None:
    """List recent test runs."""
    typer.echo("run list – not yet implemented", err=True)
    raise typer.Exit(code=1)
