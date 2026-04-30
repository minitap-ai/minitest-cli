"""App-knowledge commands: get and update an app's AppKnowledge prompt.

- ``get`` reads from ``GET /api/v1/apps/{app_id}/test-config`` and extracts the
  ``app_knowledge`` field. testing-service has no dedicated GET endpoint for
  app knowledge alone — the test-config response carries the latest version.
- ``update`` calls ``PUT /api/v1/apps/{app_id}/app-knowledge`` with body
  ``{"content": "..."}`` and returns the new ``version_number``.
"""

from pathlib import Path
from typing import Annotated, Any

import typer

from minitest_cli.commands.app_knowledge_helpers import (
    fetch_app_knowledge,
    update_app_knowledge,
)
from minitest_cli.core.auth import require_auth
from minitest_cli.core.config import Settings
from minitest_cli.utils.output import (
    print_error,
    print_info,
    print_json,
    print_success,
)

app = typer.Typer(name="app-knowledge", help="Read and update an app's AppKnowledge.")


@app.callback()
def _callback() -> None:
    """App-knowledge operations."""


def _get_settings() -> Settings:
    return typer.Context.settings  # type: ignore[attr-defined]


def _is_json_mode() -> bool:
    return typer.Context.json_mode  # type: ignore[attr-defined]


@app.command(name="get")
def get_app_knowledge(
    app_id: Annotated[
        str,
        typer.Option(
            "--app",
            help="App ID to read AppKnowledge for. Required.",
        ),
    ],
) -> None:
    """Read the current AppKnowledge content for an app.

    Without ``--json``, prints the markdown content to stdout. With ``--json``,
    prints the full record (including ``versionNumber`` if available).
    """
    settings = _get_settings()
    json_mode = _is_json_mode()
    require_auth(settings)

    record = fetch_app_knowledge(settings, app_id)

    if json_mode:
        print_json(record)
        return

    content = record.get("content")
    if not content:
        print_info("No AppKnowledge content set for this app.")
        return
    print(content)  # noqa: T201


@app.command(name="update")
def update_app_knowledge_command(
    app_id: Annotated[
        str,
        typer.Option(
            "--app",
            help="App ID to update AppKnowledge for. Required.",
        ),
    ],
    content: Annotated[
        str | None,
        typer.Option(
            "--content",
            help="New AppKnowledge markdown content (inline string).",
        ),
    ] = None,
    content_file: Annotated[
        Path | None,
        typer.Option(
            "--content-file",
            help="Path to a file whose contents become the new AppKnowledge.",
            exists=True,
            readable=True,
            dir_okay=False,
        ),
    ] = None,
) -> None:
    """Create a new version of the AppKnowledge prompt for an app.

    Either ``--content`` or ``--content-file`` must be provided (not both).
    Prints the new version number to stdout. With ``--json``, prints the full
    response record.
    """
    settings = _get_settings()
    json_mode = _is_json_mode()
    require_auth(settings)

    body = _resolve_content(content, content_file)
    record: dict[str, Any] = update_app_knowledge(settings, app_id, body)

    if json_mode:
        print_json(record)
        return

    version_number = record.get("versionNumber") or record.get("version_number")
    if version_number is None:
        print_error("Backend response did not include a version number.")
        raise typer.Exit(code=1)
    print_success(f"AppKnowledge updated (version {version_number}).")
    print(version_number)  # noqa: T201


def _resolve_content(content: str | None, content_file: Path | None) -> str:
    if content is None and content_file is None:
        print_error("Provide --content or --content-file.")
        raise typer.Exit(code=1)
    if content is not None and content_file is not None:
        print_error("Use either --content or --content-file, not both.")
        raise typer.Exit(code=1)
    if content is not None:
        if content == "":
            print_error("--content must not be empty.")
            raise typer.Exit(code=1)
        return content
    assert content_file is not None  # noqa: S101  for type checkers
    text = content_file.read_text(encoding="utf-8")
    if not text:
        print_error(f"--content-file is empty: {content_file}")
        raise typer.Exit(code=1)
    return text
