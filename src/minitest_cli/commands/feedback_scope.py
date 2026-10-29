"""`--scope` for "not a bug" feedback: how far the rule Mini learns from it reaches.

``scenario`` (the server default) keeps the rule on the issue's scenario,
``tag:<name-or-id>`` applies it to every scenario carrying that tag, ``app`` to the
whole app. Mirrors the scope picker next to "Not a bug" in the webapp.
"""

from typing import Annotated, Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.tags_helpers import resolve_tag_ids
from minitest_cli.utils.output import print_error

ScopeOpt = Annotated[
    str | None,
    typer.Option(
        "--scope",
        help="Where the rule learned from this feedback applies: scenario (default), "
        "tag:<name-or-id>, or app.",
    ),
]


def check_scope(raw: str | None) -> None:
    """Reject a malformed --scope before any request is sent."""
    if raw is None or raw in ("scenario", "app"):
        return
    kind, _, ref = raw.partition(":")
    if kind == "tag" and ref.strip():
        return
    print_error("--scope takes scenario, app, or tag:<name-or-id>.")
    raise typer.Exit(code=1)


async def scope_body(client: ApiClient, app_id: str, raw: str | None) -> dict[str, Any] | None:
    """The request's ``scope`` object, resolving a tag name to its id."""
    check_scope(raw)
    if raw is None:
        return None
    if raw in ("scenario", "app"):
        return {"kind": raw}
    [tag_id] = await resolve_tag_ids(client, app_id, [raw.partition(":")[2].strip()])
    return {"kind": "tag", "id": tag_id}


def with_scope(body: dict[str, Any], scope: dict[str, Any] | None) -> dict[str, Any]:
    return {**body, "scope": scope} if scope is not None else body
