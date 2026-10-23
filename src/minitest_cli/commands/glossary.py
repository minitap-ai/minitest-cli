"""`minitest glossary`: the app's product terms, their meaning and aliases."""

from typing import Annotated, Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.knowledge_helpers import (
    app_path,
    call_for_app,
    check_response,
    describe_actor,
)
from minitest_cli.commands.user_story_helpers import EXIT_NOT_FOUND, is_json_mode
from minitest_cli.utils.confirm import confirm_or_exit
from minitest_cli.utils.output import output, print_error, print_info, print_success, print_table

app = typer.Typer(
    name="glossary",
    help="Glossary: product terms Mini must understand, with their meaning and aliases.",
    no_args_is_help=True,
)

TermRef = Annotated[str, typer.Argument(help="Term ID, or the term itself (case-insensitive).")]
AliasOption = Annotated[
    list[str] | None,
    typer.Option("--alias", help="Other name for the term (repeatable; replaces the aliases)."),
]


async def _fetch_terms(client: ApiClient, app_id: str) -> list[dict[str, Any]]:
    resp = await client.get(app_path(app_id, "glossary"))
    check_response(resp, resource="Glossary")
    return resp.json().get("terms", [])


def _find_term(terms: list[dict[str, Any]], ref: str) -> dict[str, Any]:
    wanted = ref.strip().casefold()
    for term in terms:
        if term.get("id") == ref or str(term.get("term", "")).casefold() == wanted:
            return term
    print_error(f"Glossary term not found: {ref}. Run `minitest glossary list` to see the terms.")
    raise typer.Exit(code=EXIT_NOT_FOUND)


@app.command(name="list")
def list_terms() -> None:
    """List every term with its meaning, aliases and last author."""
    terms = call_for_app(_fetch_terms)
    if is_json_mode():
        output({"terms": terms}, json_mode=True)
        return
    if not terms:
        print_info("No glossary terms yet. Add one with `minitest glossary add`.")
        return
    rows = [
        [
            t.get("term", ""),
            t.get("meaning", ""),
            ", ".join(t.get("aliases") or []),
            describe_actor(t.get("actor")),
            t.get("id", ""),
        ]
        for t in terms
    ]
    print_table(["Term", "Meaning", "Aliases", "Last edited by", "ID"], rows, title="Glossary")


@app.command(name="add")
def add_term(
    term: Annotated[str, typer.Option("--term", help="The product term, as users say it.")],
    meaning: Annotated[str, typer.Option("--meaning", help="What the term means in this app.")],
    alias: AliasOption = None,
) -> None:
    """Add a term to the glossary."""
    body = {"term": term, "meaning": meaning, "aliases": alias or []}

    async def _add(client: ApiClient, app_id: str) -> dict[str, Any]:
        resp = await client.post(app_path(app_id, "glossary"), json=body)
        check_response(resp, resource="Glossary")
        return resp.json()

    created = call_for_app(_add)
    if not is_json_mode():
        print_success(f"Glossary term added: {created.get('term')} ({created.get('id')})")
    output(created, json_mode=is_json_mode())


@app.command(name="update")
def update_term(
    term_ref: TermRef,
    term: Annotated[str | None, typer.Option("--term", help="Rename the term.")] = None,
    meaning: Annotated[str | None, typer.Option("--meaning", help="New meaning.")] = None,
    alias: AliasOption = None,
    clear_aliases: Annotated[
        bool, typer.Option("--clear-aliases", help="Remove every alias. Excludes --alias.")
    ] = False,
) -> None:
    """Change a term's name, meaning or aliases."""
    if clear_aliases and alias:
        print_error("Use either --alias or --clear-aliases, not both.")
        raise typer.Exit(code=1)
    fields: dict[str, Any] = {"term": term, "meaning": meaning}
    fields["aliases"] = [] if clear_aliases else alias or None
    payload = {key: value for key, value in fields.items() if value is not None}
    if not payload:
        print_error("Provide at least one of --term, --meaning, --alias or --clear-aliases.")
        raise typer.Exit(code=1)

    async def _update(client: ApiClient, app_id: str) -> dict[str, Any]:
        found = _find_term(await _fetch_terms(client, app_id), term_ref)
        resp = await client.patch(app_path(app_id, f"glossary/{found['id']}"), json=payload)
        check_response(resp, resource="Glossary term")
        return resp.json()

    updated = call_for_app(_update)
    if not is_json_mode():
        print_success(f"Glossary term updated: {updated.get('term')}")
    output(updated, json_mode=is_json_mode())


@app.command(name="remove")
def remove_term(
    term_ref: TermRef,
    yes: Annotated[bool, typer.Option("--yes", help="Confirm the removal.")] = False,
) -> None:
    """Remove a term from the glossary (kept in its history)."""
    confirm_or_exit(yes, f"Removing glossary term {term_ref!r}")

    async def _remove(client: ApiClient, app_id: str) -> dict[str, Any]:
        found = _find_term(await _fetch_terms(client, app_id), term_ref)
        resp = await client.delete(app_path(app_id, f"glossary/{found['id']}"))
        check_response(resp, resource="Glossary term")
        return found

    removed = call_for_app(_remove)
    if is_json_mode():
        output({"removed": True, "id": removed["id"], "term": removed["term"]}, json_mode=True)
    else:
        print_success(f"Glossary term removed: {removed['term']}")
