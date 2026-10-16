"""`minitest draft message|messages|stop`: talk to Mini about a draft."""

import uuid
from pathlib import Path
from typing import Annotated, Any

import typer

from minitest_cli.commands.draft_helpers import call, draft_path, resolve_target
from minitest_cli.commands.draft_render import MESSAGE_TABLE_HEADERS, read_text
from minitest_cli.utils.output import print_info, print_json, print_success, print_table


def _message_row(message: dict[str, Any]) -> list[str]:
    return [str(message.get("createdAt", "-")), str(message.get("role", "-")), message["content"]]


def register(app: typer.Typer) -> None:
    @app.command(name="message")
    def post_message(
        draft_id: Annotated[str, typer.Argument(help="Draft ID.")],
        message: Annotated[str | None, typer.Option("--message", help="What to tell Mini.")] = None,
        message_file: Annotated[
            Path | None,
            typer.Option("--message-file", help="Read the message from a file (- = stdin)."),
        ] = None,
        client_message_id: Annotated[
            str | None,
            typer.Option(
                "--client-message-id", help="Re-send with the same id to never post it twice."
            ),
        ] = None,
    ) -> None:
        """Send Mini a follow-up message; Mini answers it in the background, in order."""
        text = read_text(message, message_file, flag="message", required=True)
        target = resolve_target()
        message_id = client_message_id or f"cli-{uuid.uuid4()}"
        posted = call(
            target,
            "POST",
            draft_path(draft_id, "/messages"),
            retry=True,
            json={"message": text, "clientMessageId": message_id},
        )
        if target.json_mode:
            print_json(posted)
            return
        verb = "Sent" if posted.get("created") else "Already sent"
        print_success(f"{verb} (client message id: {message_id}).")
        print_info(f"Wait for Mini's reply with `minitest draft get {draft_id} --watch`.")

    @app.command(name="messages")
    def list_messages(
        draft_id: Annotated[str, typer.Argument(help="Draft ID.")],
        last: Annotated[
            int | None, typer.Option("--last", min=1, help="Only the last N messages.")
        ] = None,
    ) -> None:
        """Read the conversation with Mini, oldest first."""
        target = resolve_target()
        body = call(target, "GET", draft_path(draft_id, "/messages"), retry=True)
        messages = body.get("messages", [])
        if last is not None:
            messages = messages[-last:]
        if target.json_mode:
            print_json(messages)
            return
        if not messages:
            print_info("No messages yet.")
            return
        print_table(MESSAGE_TABLE_HEADERS, [_message_row(m) for m in messages])

    @app.command(name="stop")
    def stop_turn(draft_id: Annotated[str, typer.Argument(help="Draft ID.")]) -> None:
        """Interrupt what Mini is writing right now."""
        target = resolve_target()
        body = call(target, "POST", draft_path(draft_id, "/stop"))
        if target.json_mode:
            print_json(body)
            return
        if body.get("stopped"):
            print_success("Mini stopped.")
        else:
            print_info("Mini was not writing.")
