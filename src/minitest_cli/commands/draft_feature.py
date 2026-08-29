"""Draft-feature commands: list, create, delete.

A draft feature is a branch of the app's test suite — it holds a delta against
main rather than a copy of it, so `show` is the only way to see what it changes.
"""

from typing import Annotated

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands import draft_feature_apply, draft_feature_show
from minitest_cli.commands.draft_feature_helpers import (
    DRAFT_FEATURE_TABLE_HEADERS,
    base_path,
    format_draft_feature_row,
    handle_response_error,
)
from minitest_cli.commands.run_helpers import ensure_uuid, resolve_app, run_api_call
from minitest_cli.models.draft_feature import DraftFeatureResponse, DraftFeatureStatus
from minitest_cli.utils.output import output, print_error, print_info, print_success, print_table

app = typer.Typer(name="df", help="Draft features — branches of the app's test suite.")
draft_feature_show.register(app)
draft_feature_apply.register(app)


@app.command(name="list")
def list_draft_features(
    status_filter: Annotated[
        list[DraftFeatureStatus] | None,
        typer.Option("--status", help="Filter by status (repeatable)."),
    ] = None,
) -> None:
    """List the branches of the active app's test suite."""
    settings, app_id, json_mode = resolve_app()
    params: dict[str, object] = {}
    if status_filter:
        params["status"] = [status.value for status in status_filter]

    async def _list() -> list[DraftFeatureResponse]:
        async with ApiClient(settings) as client:
            resp = await client.get(base_path(app_id), params=params)
            handle_response_error(resp, resource="Draft features")
            return [DraftFeatureResponse.model_validate(item) for item in resp.json()]

    features = run_api_call(_list())

    if json_mode:
        output([f.model_dump(mode="json", by_alias=True) for f in features], json_mode=True)
        return
    if not features:
        print_info("No draft features found.")
        return
    print_table(
        DRAFT_FEATURE_TABLE_HEADERS,
        [format_draft_feature_row(f) for f in features],
        title=f"Draft features ({len(features)})",
    )


@app.command(name="create")
def create_draft_feature(
    title: Annotated[str, typer.Option("--title", help="How callers recognise this branch.")],
    description: Annotated[
        str | None,
        typer.Option("--description", help="What product change the branch describes."),
    ] = None,
) -> None:
    """Open a branch off the app's main suite."""
    settings, app_id, json_mode = resolve_app()
    body: dict[str, object] = {"title": title}
    if description is not None:
        body["description"] = description

    async def _create() -> DraftFeatureResponse:
        async with ApiClient(settings) as client:
            resp = await client.post(base_path(app_id), json=body)
            handle_response_error(resp)
            return DraftFeatureResponse.model_validate(resp.json())

    feature = run_api_call(_create())
    if not json_mode:
        print_success(f"Draft feature created: {feature.id}")
    output(feature.model_dump(mode="json", by_alias=True), json_mode=json_mode)


@app.command(name="delete")
def delete_draft_feature(
    draft_feature_id: Annotated[str, typer.Argument(help="Draft feature ID.")],
    force: Annotated[bool, typer.Option("--force", help="Skip confirmation.")] = False,
) -> None:
    """Abandon a branch. Requires --force flag."""
    settings, app_id, json_mode = resolve_app()
    if not force:
        print_error("Delete requires --force flag.")
        raise typer.Exit(code=1)
    ensure_uuid(draft_feature_id, kind="draft feature id")

    async def _delete() -> DraftFeatureResponse:
        async with ApiClient(settings) as client:
            resp = await client.delete(f"{base_path(app_id)}/{draft_feature_id}")
            handle_response_error(resp)
            return DraftFeatureResponse.model_validate(resp.json())

    feature = run_api_call(_delete())
    if json_mode:
        output(feature.model_dump(mode="json", by_alias=True), json_mode=True)
    else:
        print_success(f"Draft feature abandoned: {feature.id} (status: {feature.status.value})")
