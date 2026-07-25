"""Identity-preserving single-criterion edits: --set-criterion / --revert-criterion.

Unlike ``--criteria`` (full replace, which severs version history when content
no longer matches), these edits send ``{id, content}`` for the targeted
criterion so the server creates a new version of the SAME criterion — exactly
what the webapp does. Reverts additionally stamp ``revertFromVersionId`` with
the exact version text so the server records ``source=REVERT``.
"""

from typing import Annotated, Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.user_story_helpers import handle_response_error
from minitest_cli.utils.output import print_error

SetCriterion = tuple[str, str]
RevertCriterion = tuple[str, str]

SetCriterionOption = Annotated[
    list[str] | None,
    typer.Option(
        "--set-criterion",
        help=(
            "Reword ONE criterion keeping its identity/version history: "
            "<criterion-id-or-index>=<new text> (repeatable). Prefer this "
            "over --criteria for rewording."
        ),
    ),
]

RevertCriterionOption = Annotated[
    list[str] | None,
    typer.Option(
        "--revert-criterion",
        help=(
            "Restore a criterion to a previous version's exact text: "
            "<criterion-id-or-index>=<version_id> (repeatable)."
        ),
    ),
]


def parse_criterion_edit_flags(
    set_criterion: list[str] | None,
    revert_criterion: list[str] | None,
    *,
    criteria: list[str] | None,
    add_criteria: list[str] | None,
) -> tuple[list[SetCriterion], list[RevertCriterion]]:
    """Parse both flag lists, rejecting combination with full-replace flags."""
    set_criteria = [parse_set_criterion(v) for v in (set_criterion or [])]
    revert_criteria = [parse_revert_criterion(v) for v in (revert_criterion or [])]
    if (set_criteria or revert_criteria) and (criteria is not None or add_criteria):
        print_error("Use --set-criterion/--revert-criterion without --criteria/--add-criteria.")
        raise typer.Exit(code=1)
    return set_criteria, revert_criteria


def _parse_pair(value: str, *, flag: str, expected: str) -> tuple[str, str]:
    selector, sep, payload = value.partition("=")
    selector, payload = selector.strip(), payload.strip()
    if not sep or not selector or not payload:
        print_error(f"Invalid {flag} '{value}'. Expected {expected}.")
        raise typer.Exit(code=1)
    return selector, payload


def parse_set_criterion(value: str) -> SetCriterion:
    """Parse ``<criterion-id-or-index>=<new text>`` (text may contain '=')."""
    return _parse_pair(value, flag="--set-criterion", expected="<criterion-id-or-index>=<text>")


def parse_revert_criterion(value: str) -> RevertCriterion:
    """Parse ``<criterion-id-or-index>=<version_id>``."""
    return _parse_pair(
        value, flag="--revert-criterion", expected="<criterion-id-or-index>=<version_id>"
    )


def _resolve_item(items: list[dict[str, Any]], selector: str) -> dict[str, Any]:
    if selector.isdigit():
        index = int(selector)
        if index < 1 or index > len(items):
            print_error(f"Criterion index {index} out of range (1-{len(items)}).")
            raise typer.Exit(code=1)
        item = items[index - 1]
    else:
        item = next((i for i in items if i.get("id") == selector), None)
        if item is None:
            print_error(f"No criterion matches id '{selector}'.")
            raise typer.Exit(code=1)
    if not item.get("id"):
        print_error("Cannot edit a criterion without a stable id.")
        raise typer.Exit(code=1)
    return item


def apply_set_criterion_edits(
    items: list[dict[str, Any]], edits: list[SetCriterion]
) -> list[dict[str, Any]]:
    """Rewrite each targeted criterion's content in place, keeping its id."""
    for selector, text in edits:
        item = _resolve_item(items, selector)
        item["content"] = text
    return items


async def apply_revert_criterion_edits(
    client: ApiClient,
    app_id: str,
    items: list[dict[str, Any]],
    reverts: list[RevertCriterion],
) -> list[dict[str, Any]]:
    """Restore each targeted criterion to a named version's exact text.

    The server only stamps ``source=REVERT`` when the submitted content matches
    the named version verbatim, so the text is fetched rather than user-supplied.
    """
    for selector, version_id in reverts:
        item = _resolve_item(items, selector)
        resp = await client.get(f"/api/v1/apps/{app_id}/criteria/{item['id']}/versions")
        handle_response_error(resp)
        versions = resp.json()
        version = next((v for v in versions if str(v.get("id")) == version_id), None)
        if version is None:
            print_error(f"Version '{version_id}' not found for criterion '{item['id']}'.")
            raise typer.Exit(code=1)
        item["content"] = version["content"]
        item["revertFromVersionId"] = version_id
    return items
