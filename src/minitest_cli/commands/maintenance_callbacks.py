"""Callback subcommands for an open CLI maintenance run."""

from pathlib import Path
from typing import Annotated

import typer

from minitest_cli.commands.maintenance_helpers import (
    change_idempotency_key,
    post_callback,
)
from minitest_cli.commands.maintenance_state import load_handle, read_json_file
from minitest_cli.commands.run_helpers import get_settings, run_api_call
from minitest_cli.utils.output import print_info, print_json


def register_callback_commands(app: typer.Typer) -> None:
    @app.command()
    def affected(
        file: Annotated[Path, typer.Option("--file", help="JSON file: {stories:[...]}.")],
    ) -> None:
        """Declare which stories the change affects (idempotent per run)."""
        _post_file(file, sub_path="affected-stories")

    @app.command()
    def change(
        file: Annotated[
            Path,
            typer.Option("--file", help="JSON file: one maintenance change."),
        ],
    ) -> None:
        """Post one proposed maintenance change to the release queue."""
        payload = read_json_file(file)
        result = _post_payload(
            payload,
            sub_path="changes",
            idempotency_key=change_idempotency_key(payload),
        )
        print_json(result or {"status": "skipped"})

    @app.command()
    def divergence(
        file: Annotated[
            Path,
            typer.Option("--file", help="JSON file: one divergence."),
        ],
    ) -> None:
        """Post a spec-vs-code divergence finding."""
        _post_file(file, sub_path="divergences")

    @app.command()
    def status(
        phase: Annotated[str, typer.Option("--phase", help="triage|writing|finalizing")],
        message: Annotated[str, typer.Option("--message", help="Short progress line.")],
        progress: Annotated[int | None, typer.Option("--progress", help="0-100.")] = None,
    ) -> None:
        """Post a progress status update."""
        payload: dict[str, object] = {"phase": phase, "message": message}
        if progress is not None:
            payload["progressPct"] = progress
        _post_payload(payload, sub_path="status-updates")
        print_info(f"status: {phase} — {message}")


def _post_file(file: Path, *, sub_path: str) -> None:
    payload = read_json_file(file)
    print_json(_post_payload(payload, sub_path=sub_path) or {})


def _post_payload(
    payload: dict[str, object],
    *,
    sub_path: str,
    idempotency_key: str | None = None,
) -> dict[str, object] | None:
    handle = load_handle()
    return run_api_call(
        post_callback(
            settings=get_settings(),
            run_id=handle["runId"],
            token=handle["token"],
            sub_path=sub_path,
            payload=payload,
            idempotency_key=idempotency_key,
        )
    )
