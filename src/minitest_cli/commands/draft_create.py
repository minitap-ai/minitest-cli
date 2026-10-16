"""`minitest draft create`: open a draft with a first message for Mini."""

import uuid
from pathlib import Path
from typing import Annotated

import typer

from minitest_cli.commands.draft_helpers import DRAFTS_PATH, call, resolve_target
from minitest_cli.commands.draft_render import read_text, show_draft
from minitest_cli.utils.output import print_info, print_success, print_warning


def register(app: typer.Typer) -> None:
    @app.command(name="create")
    def create_draft(
        message: Annotated[
            str | None, typer.Option("--message", help="What you want Mini to change.")
        ] = None,
        message_file: Annotated[
            Path | None,
            typer.Option("--message-file", help="Read the message from a file (- = stdin)."),
        ] = None,
        title: Annotated[
            str | None, typer.Option("--title", help="Draft title (Mini names it otherwise).")
        ] = None,
        auto_check: Annotated[
            bool,
            typer.Option("--auto-check/--no-auto-check", help="Check each change Mini writes."),
        ] = False,
        auto_merge: Annotated[
            bool,
            typer.Option(
                "--auto-merge/--no-auto-merge", help="Merge on its own once proven and ready."
            ),
        ] = False,
        idempotency_key: Annotated[
            str | None,
            typer.Option(
                "--idempotency-key", help="Re-run with the same key to get the same draft back."
            ),
        ] = None,
    ) -> None:
        """Open a draft with a first message; Mini starts working on it right away."""
        text = read_text(message, message_file, flag="message", required=True)
        if auto_merge and not auto_check:
            print_warning(
                "--auto-merge only merges proven changes; add --auto-check or run `draft check`."
            )
        target = resolve_target()
        key = idempotency_key or f"cli-{uuid.uuid4()}"
        body: dict[str, object] = {
            "tenantId": target.tenant_id,
            "appId": target.app_id,
            "message": text,
            "autoCheck": auto_check,
            "autoMerge": auto_merge,
            "idempotencyKey": key,
        }
        if title is not None:
            body["title"] = title
        draft = call(target, "POST", DRAFTS_PATH, retry=True, json=body)
        print_success(f"Draft {draft['id']} opened; Mini is on it.")
        print_info(f"Idempotency key: {key} — reuse it with --idempotency-key to retry safely.")
        print_info(f"Follow it with `minitest draft get {draft['id']} --watch`.")
        show_draft(draft, json_mode=target.json_mode)
