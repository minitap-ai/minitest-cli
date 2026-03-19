"""Authentication commands: login, logout, status."""

import typer

app = typer.Typer(name="auth", help="Authentication management.")


@app.command()
def login() -> None:
    """Authenticate with the Minitest platform."""
    typer.echo("auth login – not yet implemented", err=True)
    raise typer.Exit(code=1)


@app.command()
def logout() -> None:
    """Remove stored credentials."""
    typer.echo("auth logout – not yet implemented", err=True)
    raise typer.Exit(code=1)


@app.command()
def status() -> None:
    """Show current authentication status."""
    typer.echo("auth status – not yet implemented", err=True)
    raise typer.Exit(code=1)
