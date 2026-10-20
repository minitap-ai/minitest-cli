"""``secret extract``: move a literal credential out of a scenario into the vault.

The server never reads a value out of a scenario, so the CLI does it: it fetches the
scenario (which the caller can already read), lints it, takes the leaked literal locally,
creates the secret with it, then PATCHes the scenario with every occurrence replaced by
``{{secret:NAME}}``. The literal is never printed, only its position and length.
"""

import re
from typing import Annotated, Any, NoReturn

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.secret_helpers import (
    JsonOption,
    SecretKind,
    command_context,
    reference,
    refuse_agent_context,
    request,
    secrets_path,
    validate_name,
)
from minitest_cli.commands.secret_lint import fetch_story, lint_text, position, story_sources
from minitest_cli.commands.user_story_criteria import extract_criteria_items
from minitest_cli.commands.user_story_helpers import base_path, handle_response_error, run_api_call
from minitest_cli.utils.output import err_console, print_error, print_json, print_success
from minitest_cli.utils.output import print_info, print_warning

_LABELLED = re.compile(
    r"^\s*(?:password|passwd|pwd|pass|passcode|pin|otp|code|token|secret|api[ _-]?key)"
    r"(?:\s*[:=]\s*|\s+is\s+|\s+)(?P<value>\S.*?)\s*$",
    re.IGNORECASE | re.DOTALL,
)
MIN_LITERAL_LENGTH = 4


def literal_of(text: str, leak: dict[str, Any]) -> str:
    """The leaked literal; a ``password: xxx`` heuristic span keeps only the value."""
    raw = text[int(leak["start"]) : int(leak["end"])].strip().strip("\"'`")
    match = _LABELLED.match(raw)
    return match.group("value").strip("\"'`") if match else raw


def _fail(message: str) -> NoReturn:
    print_error(message)
    raise typer.Exit(code=1)


def _candidates(results: list[tuple[str, str, dict[str, Any]]]) -> list[tuple[str, str, str]]:
    seen: dict[str, tuple[str, str, str]] = {}
    for label, text, result in results:
        for leak in result.get("leaks") or []:
            literal = literal_of(text, leak) if not leak.get("secret") else ""
            if len(literal) >= MIN_LITERAL_LENGTH and literal not in seen:
                seen[literal] = (label, position(text, int(leak["start"])), literal)
    return list(seen.values())


def _patch_body(story: dict[str, Any], literal: str, ref: str) -> tuple[dict[str, Any], int]:
    body: dict[str, Any] = {}
    count = (story.get("description") or "").count(literal)
    if count:
        body["description"] = story["description"].replace(literal, ref)
    items = extract_criteria_items(story)
    hits = sum(item["content"].count(literal) for item in items)
    if hits:
        body["acceptanceCriteria"] = [
            {**item, "content": item["content"].replace(literal, ref)} for item in items
        ]
    return body, count + hits


def register(app: typer.Typer) -> None:

    @app.command(name="extract")
    def extract(
        scenario_id: Annotated[str, typer.Argument(help="Scenario ID holding the literal.")],
        name: Annotated[str, typer.Option("--as", help="Name of the secret to create.")],
        kind: Annotated[SecretKind, typer.Option("--kind", help="password, totp, token or text.")],
        note: Annotated[str | None, typer.Option("--note", help="What it is for.")] = None,
        leak: Annotated[
            int | None, typer.Option("--leak", help="Which leak to extract (1-based), if several.")
        ] = None,
        dry_run: Annotated[bool, typer.Option("--dry-run", help="Show the plan only.")] = False,
        json_flag: JsonOption = False,
    ) -> None:
        """Create a secret from a literal leaked in a scenario and replace it by its reference."""
        refuse_agent_context()
        validate_name(name)
        if kind is SecretKind.card:
            _fail("A card has several fields: create it with `secret set --kind card` instead.")
        settings, json_mode, app_id = command_context(json_flag)
        ref = reference(name)
        story_path = f"{base_path(app_id)}/{scenario_id}"

        async def _run() -> dict[str, Any]:
            async with ApiClient(settings) as client:
                vault = await request(client, "GET", secrets_path(app_id), collection=True) or {}
                if any(s.get("name") == name for s in vault.get("secrets") or []):
                    _fail(f"A secret named {name} already exists; pick another --as name.")
                story = await fetch_story(client, app_id, scenario_id)
                results = [
                    (lb, tx, await lint_text(client, app_id, tx)) for lb, tx in story_sources(story)
                ]
                found = _candidates(results)
                if not found:
                    _fail("No literal secret found in this scenario (see `minitest secret lint`).")
                if (leak is None and len(found) > 1) or (
                    leak is not None and not 0 < leak <= len(found)
                ):
                    print_error(f"{len(found)} literals found; choose one with --leak N:")
                    for i, (label, at, literal) in enumerate(found, start=1):
                        err_console.print(f"  {i}. {label} at {at} ({len(literal)} characters)")
                    raise typer.Exit(code=1)
                label, at, literal = found[(leak or 1) - 1]
                body, count = _patch_body(story, literal, ref)
                plan = {"secret": name, "source": label, "at": at, "replacements": count}
                if dry_run:
                    return {**plan, "dryRun": True}
                secret_body: dict[str, Any] = {"kind": kind.value, "value": literal}
                if note is not None:
                    secret_body["note"] = note
                await request(client, "PUT", f"{secrets_path(app_id)}/{name}", json=secret_body)
                resp = await client.patch(story_path, json=body)
                if resp.status_code >= 400:
                    print_error(f"Secret {name} was created but the scenario was not updated.")
                handle_response_error(resp)
                return plan

        plan = run_api_call(_run())
        if json_mode:
            print_json(plan)
            return
        where = f"{plan['source']} at {plan['at']}"
        if plan.get("dryRun"):
            print_info(
                f"Would create {name} from the literal in {where} and replace "
                f"{plan['replacements']} occurrence(s) with {ref}."
            )
            return
        print_success(
            f"Secret {name} created; {plan['replacements']} occurrence(s) now read {ref}."
        )
        print_warning(
            "Older scenario versions and past run logs may still hold the literal: "
            "rotate the credential if it is sensitive."
        )
