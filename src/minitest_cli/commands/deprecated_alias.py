from typing import Any

import typer

from minitest_cli.utils.output import print_error, print_warning


def deprecated_alias(source: typer.Typer, *, old_name: str) -> typer.Typer:
    """Expose ``source``'s commands under a hidden legacy name that warns on stderr."""
    new_name = source.info.name
    alias = typer.Typer(name=old_name, help=f"Deprecated: use `minitest {new_name}`.", hidden=True)

    @alias.callback()
    def _warn() -> None:
        print_warning(f"`minitest {old_name}` is deprecated; use `minitest {new_name}` instead.")

    alias.registered_commands = source.registered_commands
    return alias


def deprecated_option(*param_decls: str, new_flag: str) -> Any:
    """A hidden option kept for a renamed flag; pair it with ``merge_deprecated_option``."""
    return typer.Option(*param_decls, hidden=True, help=f"Deprecated alias for {new_flag}.")


def merge_deprecated_option[T](
    new: T | None, old: T | None, *, old_flag: str, new_flag: str
) -> T | None:
    """Return the renamed flag's value, falling back to its deprecated alias with a warning."""
    if old is None:
        return new
    print_warning(f"{old_flag} is deprecated; use {new_flag} instead.")
    if new is None:
        return old
    if isinstance(new, list) and isinstance(old, list):
        return [*new, *old]  # type: ignore[return-value]
    print_error(f"Use either {new_flag} or {old_flag}, not both.")
    raise typer.Exit(code=1)
