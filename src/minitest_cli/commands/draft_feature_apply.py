"""`minitest df apply` — post a changeset file to a branch."""

from pathlib import Path
from typing import Annotated

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.draft_feature_helpers import (
    CREATED_STORY_HEADERS,
    base_path,
    handle_response_error,
    read_changeset_file,
)
from minitest_cli.commands.run_helpers import ensure_uuid, resolve_app, run_api_call
from minitest_cli.models.draft_feature import ApplyChangesetResponse
from minitest_cli.utils.output import output, print_success, print_table


def register(app: typer.Typer) -> None:
    @app.command(name="apply")
    def apply_changeset(
        draft_feature_id: Annotated[str, typer.Argument(help="Draft feature ID.")],
        changeset: Annotated[
            Path,
            typer.Option(
                "--changeset",
                help="JSON file: {expectedMainRev, idempotencyKey, ops: [...]}.",
            ),
        ],
    ) -> None:
        """Apply a batch of branch operations atomically, from a JSON request body."""
        settings, app_id, json_mode = resolve_app()
        ensure_uuid(draft_feature_id, kind="draft feature id")
        body = read_changeset_file(changeset)

        async def _apply() -> ApplyChangesetResponse:
            async with ApiClient(settings) as client:
                resp = await client.post(
                    f"{base_path(app_id)}/{draft_feature_id}/apply",
                    json=body,
                )
                handle_response_error(resp)
                return ApplyChangesetResponse.model_validate(resp.json())

        result = run_api_call(_apply())
        if json_mode:
            output(result.model_dump(mode="json", by_alias=True), json_mode=True)
            return

        print_success(f"Changeset applied to {result.draft_feature_id}.")
        # Put mainRev back in the title and rich wraps the two-column table, splitting
        # the token the caller must copy verbatim into the next changeset.
        print_table(
            CREATED_STORY_HEADERS,
            [[tmp_id, story_id] for tmp_id, story_id in result.created.items()],
            title=f"Applied — {len(result.touched_story_ids)} story row(s) touched",
        )
        output({"mainRev": result.main_rev}, json_mode=False)
