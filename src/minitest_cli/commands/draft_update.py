"""`minitest draft update`: rename a draft or change how unattended it runs."""

from typing import Annotated

import typer

from minitest_cli.commands.draft_helpers import EXIT_GENERAL_ERROR, call, draft_path, resolve_target
from minitest_cli.commands.draft_render import show_draft
from minitest_cli.utils.output import print_error


def register(app: typer.Typer) -> None:
    @app.command(name="update")
    def update_draft(
        draft_id: Annotated[str, typer.Argument(help="Draft ID.")],
        title: Annotated[str | None, typer.Option("--title", help="New title.")] = None,
        auto_check: Annotated[
            bool | None,
            typer.Option(
                "--auto-check/--no-auto-check",
                help="Check each change Mini writes (turning it on checks what is pending now).",
            ),
        ] = None,
        auto_merge: Annotated[
            bool | None,
            typer.Option(
                "--auto-merge/--no-auto-merge",
                help="Merge on its own once every change is proven (it may merge right away).",
            ),
        ] = None,
    ) -> None:
        """Change a draft's title, auto-check or auto-merge."""
        body: dict[str, object] = {}
        if title is not None:
            body["title"] = title
        if auto_check is not None:
            body["autoCheck"] = auto_check
        if auto_merge is not None:
            body["autoMerge"] = auto_merge
        if not body:
            print_error("Nothing to update: pass --title, --[no-]auto-check or --[no-]auto-merge.")
            raise typer.Exit(code=EXIT_GENERAL_ERROR)
        target = resolve_target()
        draft = call(target, "PATCH", draft_path(draft_id), json=body)
        show_draft(draft, json_mode=target.json_mode)
