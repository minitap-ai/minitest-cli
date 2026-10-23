"""`minitest knowledge history`: who changed the Product brief, App guide or Glossary."""

from enum import StrEnum
from typing import Annotated, Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.knowledge_helpers import (
    app_path,
    call_for_app,
    check_response,
    describe_actor,
)
from minitest_cli.commands.user_story_helpers import is_json_mode
from minitest_cli.utils.output import output, print_info, print_table

app = typer.Typer(
    name="knowledge",
    help="Change history of the Product brief, App guide and Glossary.",
    no_args_is_help=True,
)


class KnowledgeElement(StrEnum):
    product_brief = "product_brief"
    app_guide = "app_guide"
    glossary = "glossary"


@app.callback()
def _callback() -> None:
    """Knowledge operations."""


@app.command(name="history")
def history(
    element: Annotated[
        KnowledgeElement | None,
        typer.Option("--element", help="Only this element (default: all three, merged)."),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", min=1, max=200, help="Max changes.")] = 20,
) -> None:
    """List recent changes, newest first, with author, channel and version."""
    elements = [element] if element else list(KnowledgeElement)

    async def _history(client: ApiClient, app_id: str) -> list[dict[str, Any]]:
        changes: list[dict[str, Any]] = []
        for wanted in elements:
            resp = await client.get(
                app_path(app_id, "knowledge/history"),
                params={"element": wanted.value, "limit": limit},
            )
            check_response(resp, resource="Knowledge history")
            changes.extend(resp.json())
        changes.sort(key=lambda change: change.get("createdAt") or "", reverse=True)
        return changes[:limit]

    changes = call_for_app(_history)
    if is_json_mode():
        output(changes, json_mode=True)
        return
    if not changes:
        print_info("No knowledge changes yet.")
        return
    rows = [
        [
            c.get("createdAt", ""),
            c.get("element", ""),
            c.get("change", ""),
            _subject(c),
            describe_actor(c.get("actor")),
            c.get("versionId", ""),
        ]
        for c in changes
    ]
    print_table(["When", "Element", "Change", "Version / term", "By", "Version ID"], rows)


def _subject(change: dict[str, Any]) -> str:
    if change.get("versionNumber") is not None:
        return f"v{change['versionNumber']}"
    after = change.get("after") if isinstance(change.get("after"), dict) else None
    before = change.get("before") if isinstance(change.get("before"), dict) else None
    snapshot = after or before or {}
    return str(snapshot.get("term") or change.get("termId") or "")
