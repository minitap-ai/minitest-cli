"""App environment-variable commands: list, get, set, unset, clear.

Values are secrets: ``list`` masks them by default (reveal with ``--show``),
and ``get`` prints a single value verbatim to stdout on purpose. Mutations
(``set``/``unset``/``clear``) require ``--yes`` so they never run unconfirmed.
"""

import asyncio
from collections.abc import Coroutine
from typing import Annotated, Any

import httpx
import typer

from minitest_cli.commands.env_helpers import (
    MASK,
    confirm_or_exit,
    delete_env_vars,
    diff_keys,
    fetch_env_vars,
    print_diff,
    put_env_vars,
    resolve_app_and_tenant,
)
from minitest_cli.core.auth import require_auth
from minitest_cli.core.config import Settings
from minitest_cli.utils.output import (
    print_error,
    print_json,
    print_success,
    print_table,
)

EXIT_NETWORK_ERROR = 3
EXIT_NOT_FOUND = 4

app = typer.Typer(name="env", help="Manage an app's environment variables.")


@app.callback()
def _callback() -> None:
    """Manage an app's environment variables."""


def _get_settings() -> Settings:
    return typer.Context.settings  # type: ignore[attr-defined]


def _is_json_mode() -> bool:
    return typer.Context.json_mode  # type: ignore[attr-defined]


def _get_app_flag() -> str | None:
    return typer.Context.app_flag  # type: ignore[attr-defined]


def _run[T](coro: Coroutine[Any, Any, T]) -> T:
    try:
        return asyncio.run(coro)
    except httpx.HTTPError as exc:
        print_error(f"Network error: {exc}")
        raise typer.Exit(code=EXIT_NETWORK_ERROR) from exc


def _context() -> tuple[Settings, str, str, bool]:
    settings = _get_settings()
    require_auth(settings)
    app_id, tenant_id = _run(resolve_app_and_tenant(settings, _get_app_flag()))
    return settings, app_id, tenant_id, _is_json_mode()


@app.command(name="list")
def list_env(
    show: Annotated[
        bool, typer.Option("--show", help="Reveal values instead of masking them.")
    ] = False,
) -> None:
    """List the app's environment variables (values masked unless --show)."""
    settings, app_id, tenant_id, json_mode = _context()
    env_vars = _run(fetch_env_vars(settings, tenant_id, app_id))

    rendered = env_vars if show else {k: MASK for k in env_vars}
    if json_mode:
        print_json(rendered)
        return
    if not env_vars:
        print_success("No environment variables configured for this app.")
        return
    rows = [[k, rendered[k]] for k in sorted(rendered)]
    print_table(["Key", "Value"], rows, title="Environment variables")


@app.command(name="get")
def get_env(key: Annotated[str, typer.Argument(help="Environment variable name.")]) -> None:
    """Print a single environment variable's value verbatim to stdout."""
    settings, app_id, tenant_id, json_mode = _context()
    env_vars = _run(fetch_env_vars(settings, tenant_id, app_id))

    if key not in env_vars:
        print_error(f"Environment variable not found: '{key}'.")
        raise typer.Exit(code=EXIT_NOT_FOUND)

    if json_mode:
        print_json({key: env_vars[key]})
        return
    print(env_vars[key])  # noqa: T201


@app.command(name="set")
def set_env(
    key: Annotated[str, typer.Argument(help="Environment variable name.")],
    value: Annotated[str, typer.Argument(help="Value to set.")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Confirm the change.")] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show the change without applying it.")
    ] = False,
) -> None:
    """Set an environment variable (creates or updates), preserving the others."""
    settings, app_id, tenant_id, json_mode = _context()
    current = _run(fetch_env_vars(settings, tenant_id, app_id))
    updated = {**current, key: value}

    _apply(settings, tenant_id, app_id, current, updated, yes, dry_run, json_mode, f"Set '{key}'")


@app.command(name="unset")
def unset_env(
    key: Annotated[str, typer.Argument(help="Environment variable name.")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Confirm the change.")] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show the change without applying it.")
    ] = False,
) -> None:
    """Remove a single environment variable, preserving the others."""
    settings, app_id, tenant_id, json_mode = _context()
    current = _run(fetch_env_vars(settings, tenant_id, app_id))
    if key not in current:
        print_error(f"Environment variable not found: '{key}'.")
        raise typer.Exit(code=EXIT_NOT_FOUND)
    updated = {k: v for k, v in current.items() if k != key}

    _apply(settings, tenant_id, app_id, current, updated, yes, dry_run, json_mode, f"Unset '{key}'")


@app.command(name="clear")
def clear_env(
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Confirm the deletion.")] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show the change without applying it.")
    ] = False,
) -> None:
    """Delete ALL environment variables for the app."""
    settings, app_id, tenant_id, json_mode = _context()
    current = _run(fetch_env_vars(settings, tenant_id, app_id))
    if not current:
        print_error("No environment variables to delete.")
        raise typer.Exit(code=EXIT_NOT_FOUND)

    _, _, removed = diff_keys(current, {})
    if dry_run:
        print_diff([], [], removed)
        if json_mode:
            print_json({"added": [], "changed": [], "removed": removed, "dryRun": True})
        return

    confirm_or_exit(yes, f"Deleting all {len(current)} environment variables")
    _run(delete_env_vars(settings, tenant_id, app_id))
    if json_mode:
        print_json({"added": [], "changed": [], "removed": removed})
        return
    print_success(f"Deleted all {len(removed)} environment variables.")


def _apply(
    settings: Settings,
    tenant_id: str,
    app_id: str,
    current: dict[str, str],
    updated: dict[str, str],
    yes: bool,
    dry_run: bool,
    json_mode: bool,
    action: str,
) -> None:
    added, changed, removed = diff_keys(current, updated)
    if dry_run:
        print_diff(added, changed, removed)
        if json_mode:
            print_json({"added": added, "changed": changed, "removed": removed, "dryRun": True})
        return

    confirm_or_exit(yes, action)
    _run(put_env_vars(settings, tenant_id, app_id, updated))
    if json_mode:
        print_json({"added": added, "changed": changed, "removed": removed})
        return
    print_success(f"{action} — {len(updated)} environment variables now set.")
