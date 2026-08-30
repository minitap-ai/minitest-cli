"""`minitest df show` — read a branch as a diff, as the suite it would run, or as its conflicts."""

from enum import StrEnum
from typing import Annotated

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.draft_feature_conflicts import print_conflicts
from minitest_cli.commands.draft_feature_helpers import (
    CHANGESET_TABLE_HEADERS,
    EFFECTIVE_EDGE_HEADERS,
    EFFECTIVE_STORY_HEADERS,
    base_path,
    format_changeset_op_row,
    handle_response_error,
)
from minitest_cli.commands.run_helpers import ensure_uuid, resolve_app, run_api_call
from minitest_cli.models.draft_feature import (
    DraftFeatureChangesetResponse,
    DraftFeatureConflictsResponse,
    EffectiveSuiteResponse,
)
from minitest_cli.utils.output import output, print_info, print_table


class ChangesetView(StrEnum):
    diff = "diff"
    effective = "effective"
    conflicts = "conflicts"


def register(app: typer.Typer) -> None:
    @app.command(name="show")
    def show_draft_feature(
        draft_feature_id: Annotated[str, typer.Argument(help="Draft feature ID.")],
        view: Annotated[
            ChangesetView,
            typer.Option(
                "--view",
                help=(
                    "diff: what the branch changes. effective: the suite it would run. "
                    "conflicts: what a rebase could not settle."
                ),
            ),
        ] = ChangesetView.diff,
    ) -> None:
        """Show a branch as a changeset, as its effective suite, or as its conflicts."""
        settings, app_id, json_mode = resolve_app()
        ensure_uuid(draft_feature_id, kind="draft feature id")
        feature_path = f"{base_path(app_id)}/{draft_feature_id}"

        if view is ChangesetView.conflicts:

            async def _conflicts() -> DraftFeatureConflictsResponse:
                async with ApiClient(settings) as client:
                    resp = await client.get(f"{feature_path}/conflicts")
                    handle_response_error(resp)
                    return DraftFeatureConflictsResponse.model_validate(resp.json())

            print_conflicts(run_api_call(_conflicts()), json_mode=json_mode)
            return

        if view is ChangesetView.effective:

            async def _effective() -> EffectiveSuiteResponse:
                async with ApiClient(settings) as client:
                    resp = await client.get(f"{feature_path}/effective-suite")
                    handle_response_error(resp)
                    return EffectiveSuiteResponse.model_validate(resp.json())

            _print_effective_suite(run_api_call(_effective()), json_mode=json_mode)
            return

        async def _diff() -> DraftFeatureChangesetResponse:
            async with ApiClient(settings) as client:
                resp = await client.get(f"{feature_path}/changeset")
                handle_response_error(resp)
                return DraftFeatureChangesetResponse.model_validate(resp.json())

        _print_changeset(run_api_call(_diff()), json_mode=json_mode)


def _print_changeset(changeset: DraftFeatureChangesetResponse, *, json_mode: bool) -> None:
    if json_mode:
        output(changeset.model_dump(mode="json", by_alias=True), json_mode=True)
        return

    feature = changeset.draft_feature
    print_info(f"{feature.title} — {feature.status.value}, rebase {feature.rebase_state.value}")
    print_info("Hand mainRev back as expectedMainRev when applying, or the apply is refused.")
    rows = [format_changeset_op_row(i, op) for i, op in enumerate(changeset.ops, start=1)]
    # Put mainRev back in the title and rich wraps it to the narrow table's width,
    # splitting the token the caller must copy verbatim ("mainRev \n 4").
    print_table(CHANGESET_TABLE_HEADERS, rows, title=f"Changeset — {len(rows)} op(s)")
    output({"mainRev": changeset.main_rev}, json_mode=False)


def _print_effective_suite(suite: EffectiveSuiteResponse, *, json_mode: bool) -> None:
    if json_mode:
        output(suite.model_dump(mode="json", by_alias=True), json_mode=True)
        return

    story_rows = [
        [str(story.ordinal), story.story_id, story.slot_id, story.origin] for story in suite.stories
    ]
    print_table(
        EFFECTIVE_STORY_HEADERS,
        story_rows,
        title=f"Effective suite — {len(story_rows)} story(ies)",
    )
    if not suite.edges:
        print_info("No dependency edges.")
        return
    edge_rows = [[edge.child_story_id, edge.parent_story_id] for edge in suite.edges]
    print_table(EFFECTIVE_EDGE_HEADERS, edge_rows, title=f"Dependencies ({len(edge_rows)})")
