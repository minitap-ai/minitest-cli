import typer

from minitest_cli.utils.output import print_warning


def deprecated_alias(source: typer.Typer, *, old_name: str) -> typer.Typer:
    """Expose ``source``'s commands under a hidden legacy name that warns on stderr."""
    new_name = source.info.name
    alias = typer.Typer(name=old_name, help=f"Deprecated: use `minitest {new_name}`.", hidden=True)

    @alias.callback()
    def _warn() -> None:
        print_warning(f"`minitest {old_name}` is deprecated; use `minitest {new_name}` instead.")

    alias.registered_commands = source.registered_commands
    return alias
