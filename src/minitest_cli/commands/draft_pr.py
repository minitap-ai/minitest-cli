"""`minitest draft link-pr|unlink-pr`: prove a draft on an open pull request's head.

A draft linked to a PR checks its scenarios on a build of the PR's head commit, before
the PR merges; Conductor builds that commit itself (every shipped platform) when no build
of it exists yet. After the PR merges, the draft follows the merge commit as usual.
"""

from typing import Annotated

import typer

from minitest_cli.commands.draft_helpers import call, draft_path, resolve_target
from minitest_cli.commands.draft_render import show_draft
from minitest_cli.utils.output import print_success

DraftIdArg = Annotated[str, typer.Argument(help="Draft ID.")]


def register(app: typer.Typer) -> None:
    @app.command(name="link-pr")
    def link_pr(
        draft_id: DraftIdArg,
        number: Annotated[int, typer.Argument(min=1, help="Pull request number.")],
        repo: Annotated[
            str | None,
            typer.Option(
                "--repo",
                help="owner/name of the PR's repository; default: the app's linked repository.",
            ),
        ] = None,
    ) -> None:
        """Check this draft on an open PR's head commit instead of waiting for its merge."""
        body: dict[str, object] = {"number": number}
        if repo is not None:
            body["repo"] = repo
        target = resolve_target()
        draft = call(target, "PUT", draft_path(draft_id, "/pr"), retry=True, json=body)
        if not target.json_mode:
            print_success(f"Draft linked to PR #{number}; `draft check` now proves its head.")
        show_draft(draft, json_mode=target.json_mode)

    @app.command(name="unlink-pr")
    def unlink_pr(draft_id: DraftIdArg) -> None:
        """Stop checking this draft on a PR's head; it checks the latest build again."""
        target = resolve_target()
        draft = call(target, "DELETE", draft_path(draft_id, "/pr"), retry=True)
        if not target.json_mode:
            print_success("Draft unlinked from its PR.")
        show_draft(draft, json_mode=target.json_mode)
