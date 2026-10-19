"""`minitest draft check|build|merge|discard|revert|not-a-bug`: act on a draft's result.

None of these prompt: each is one explicit, server-guarded step (merge refuses a draft
that is not ready, discard and revert refuse a closed one with exit 6).
"""

from collections.abc import Mapping
from enum import StrEnum
from typing import Annotated

import typer

from minitest_cli.commands.draft_helpers import call, draft_path, resolve_target
from minitest_cli.commands.run_helpers import ensure_uuid
from minitest_cli.commands.draft_render import show_draft
from minitest_cli.utils.output import print_success

ReasonOption = Annotated[str | None, typer.Option("--reason", help="Why, for Mini and the log.")]
DraftIdArg = Annotated[str, typer.Argument(help="Draft ID.")]


class BuildRef(StrEnum):
    MERGE_COMMIT = "merge_commit"
    MAIN = "main"


def _act(draft_id: str, suffix: str, body: Mapping[str, object] | None, done: str) -> None:
    target = resolve_target()
    draft = call(target, "POST", draft_path(draft_id, suffix), json=body)
    if not target.json_mode:
        print_success(done)
    show_draft(draft, json_mode=target.json_mode)


def register(app: typer.Typer) -> None:
    @app.command(name="check")
    def check_draft(
        draft_id: DraftIdArg,
        story_ids: Annotated[
            list[str] | None,
            typer.Option("--story", help="Only this draft scenario id (repeatable); default all."),
        ] = None,
        include_waiting: Annotated[
            bool,
            typer.Option(
                "--include-waiting",
                help="Also run scenarios waiting for a newer build, on the newest build there is "
                "(never with a PR-linked draft: it would skip the PR's head).",
            ),
        ] = False,
        again: Annotated[
            bool,
            typer.Option(
                "--again", help="Re-run every scenario, proven ones too (e.g. after a new push)."
            ),
        ] = False,
    ) -> None:
        """Run the draft's changed scenarios to prove them (a PR-linked draft: on the PR head)."""
        body: dict[str, object] = {"includeWaiting": include_waiting}
        if again:
            body["again"] = True
        if story_ids:
            body["storyIds"] = [ensure_uuid(s, kind="scenario id") for s in story_ids]
        _act(draft_id, "/check", body, "Check started.")

    @app.command(name="build")
    def build_draft(
        draft_id: DraftIdArg,
        ref: Annotated[
            BuildRef,
            typer.Option(
                "--ref", help="merge_commit: the merged PR's commit; main: default branch."
            ),
        ] = BuildRef.MERGE_COMMIT,
    ) -> None:
        """Build the app commit a draft waiting for a build needs."""
        _act(draft_id, "/build", {"ref": ref.value}, "Build started.")

    @app.command(name="merge")
    def merge_draft(draft_id: DraftIdArg) -> None:
        """Merge a ready draft into the live suite."""
        _act(draft_id, "/merge", None, "Draft merged.")

    @app.command(name="discard")
    def discard_draft(draft_id: DraftIdArg) -> None:
        """Throw an open draft away; the live suite is untouched."""
        _act(draft_id, "/discard", None, "Draft discarded.")

    @app.command(name="revert")
    def revert_draft(draft_id: DraftIdArg, reason: ReasonOption = None) -> None:
        """Undo a merged draft's change to the live suite."""
        _act(draft_id, "/revert", {"reason": reason} if reason else None, "Draft reverted.")

    @app.command(name="not-a-bug")
    def not_a_bug(
        draft_id: DraftIdArg,
        story_id: Annotated[str, typer.Argument(help="Scenario Mini judged an app bug.")],
        reason: ReasonOption = None,
    ) -> None:
        """Tell Mini a failure it judged an app bug is the scenario's fault; Mini fixes it."""
        ensure_uuid(story_id, kind="scenario id")
        body = {"reason": reason} if reason else None
        _act(draft_id, f"/stories/{story_id}/not-a-bug", body, "Sent back to Mini.")
