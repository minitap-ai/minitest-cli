"""Local state helpers for CLI maintenance runs."""

import json
import subprocess
from pathlib import Path
from typing import Any

import typer

from minitest_cli.utils.output import print_error

EXIT_GENERAL = 1

_HANDLE_PATH = Path.home() / ".minitest" / "maintenance_run.json"


def current_head_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],  # noqa: S603, S607
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        print_error(
            "Not a git repository (git rev-parse HEAD failed). "
            "Run maintenance from your app's repo."
        )
        raise typer.Exit(code=EXIT_GENERAL) from None
    return result.stdout.strip()


def save_handle(handle: dict[str, Any]) -> None:
    _HANDLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _HANDLE_PATH.write_text(json.dumps(handle, indent=2))
    _HANDLE_PATH.chmod(0o600)


def load_handle() -> dict[str, Any]:
    if not _HANDLE_PATH.exists():
        print_error("No open maintenance run. Run `minitest maintenance context` first.")
        raise typer.Exit(code=EXIT_GENERAL)
    return json.loads(_HANDLE_PATH.read_text())


def clear_handle() -> None:
    _HANDLE_PATH.unlink(missing_ok=True)


def read_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print_error(f"Could not read JSON file '{path}': {exc}")
        raise typer.Exit(code=EXIT_GENERAL) from exc
