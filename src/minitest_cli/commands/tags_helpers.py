"""Shared helpers for tenant tags: API path, lookup by name or id, --tag options."""

from typing import Annotated, Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.user_story_helpers import EXIT_NOT_FOUND, handle_response_error
from minitest_cli.utils.output import print_error, print_warning

TagOption = Annotated[
    list[str] | None,
    typer.Option(
        "--tag", help="Tag name (repeatable; replaces the story's tags). Unknown tags are created."
    ),
]
ClearTagsOption = Annotated[
    bool, typer.Option("--clear-tags", help="Remove every tag. Excludes --tag.")
]
LegacyTypeOption = Annotated[
    str | None,
    typer.Option("--type", hidden=True, help="Deprecated alias for --tag."),
]


def tags_path(app_id: str) -> str:
    return f"/api/v1/apps/{app_id}/tags"


async def fetch_tags(client: ApiClient, app_id: str) -> list[dict[str, Any]]:
    resp = await client.get(tags_path(app_id))
    handle_response_error(resp, resource="Tag")
    return resp.json()


def find_tag(tags: list[dict[str, Any]], ref: str) -> dict[str, Any]:
    wanted = ref.strip().casefold()
    for tag in tags:
        if tag.get("id") == ref or str(tag.get("name", "")).casefold() == wanted:
            return tag
    known = ", ".join(str(t.get("name")) for t in tags) or "none"
    print_error(f"Tag not found: {ref}. Known tags: {known}.")
    raise typer.Exit(code=EXIT_NOT_FOUND)


async def resolve_tag_ids(client: ApiClient, app_id: str, refs: list[str]) -> list[str]:
    tags = await fetch_tags(client, app_id)
    return [str(find_tag(tags, ref)["id"]) for ref in refs]


def collect_tag_names(tags: list[str] | None, legacy_type: str | None) -> list[str] | None:
    """Merge --tag and the deprecated --type into one de-duplicated list, None if neither."""
    if tags is None and legacy_type is None:
        return None
    names = list(tags or [])
    if legacy_type is not None:
        print_warning("--type is deprecated; use --tag instead.")
        names.append(legacy_type)
    unique: dict[str, str] = {}
    for name in names:
        unique.setdefault(name.strip().casefold(), name.strip())
    return list(unique.values())


def update_tag_names(
    tags: list[str] | None, legacy_type: str | None, *, clear_tags: bool
) -> list[str] | None:
    if clear_tags and (tags or legacy_type is not None):
        print_error("Use either --tag or --clear-tags, not both.")
        raise typer.Exit(code=1)
    return [] if clear_tags else collect_tag_names(tags, legacy_type)
