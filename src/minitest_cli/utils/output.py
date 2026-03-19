"""Output helpers: JSON mode vs human-friendly rendering.

Convention:
  - stdout is reserved for structured data (JSON when --json is set, tables otherwise)
  - stderr is used for diagnostics, warnings, and progress messages
"""

import json
import sys
from typing import Any

from rich.console import Console
from rich.table import Table

# stderr console for diagnostics – never captured by pipes
err_console = Console(stderr=True)


def print_json(data: Any) -> None:
    """Print a JSON-serialisable object to stdout."""
    print(json.dumps(data, indent=2, default=str))  # noqa: T201


def print_error(message: str) -> None:
    """Print an error message to stderr."""
    err_console.print(f"[bold red]Error:[/bold red] {message}")


def print_warning(message: str) -> None:
    """Print a warning message to stderr."""
    err_console.print(f"[bold yellow]Warning:[/bold yellow] {message}")


def print_success(message: str) -> None:
    """Print a success message to stderr."""
    err_console.print(f"[bold green]✓[/bold green] {message}")


def print_info(message: str) -> None:
    """Print an informational message to stderr."""
    err_console.print(f"[dim]{message}[/dim]")


def print_table(
    headers: list[str],
    rows: list[list[str]],
    title: str | None = None,
) -> None:
    """Print a rich table to stdout."""
    console = Console()
    table = Table(title=title, show_header=True, header_style="bold")
    for header in headers:
        table.add_column(header)
    for row in rows:
        table.add_row(*row)
    console.print(table)


def output(data: Any, *, json_mode: bool, headers: list[str] | None = None) -> None:
    """Unified output: JSON to stdout when json_mode is True, table otherwise.

    Args:
        data: The data to output. For JSON mode, any serialisable object.
              For table mode, should be a list of dicts.
        json_mode: Whether to output JSON.
        headers: Column headers for table mode. If None, inferred from data keys.
    """
    if json_mode:
        print_json(data)
        return

    if isinstance(data, list) and data and isinstance(data[0], dict):
        keys = headers or list(data[0].keys())
        rows = [[str(item.get(k, "")) for k in keys] for item in data]
        print_table(keys, rows)
    elif isinstance(data, dict):
        for key, value in data.items():
            print(f"{key}: {value}", file=sys.stdout)  # noqa: T201
    else:
        print(data, file=sys.stdout)  # noqa: T201
