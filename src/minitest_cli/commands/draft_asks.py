"""`minitest draft ask list|answer|decline`: answer what Mini asked on a draft.

Secret fields (``secret: true`` in an ask's answerFields) are only read from a file or
stdin (``--field-file KEY=PATH``, ``-`` for stdin) — never from the command line, where
shells and process lists keep them — and are never printed back.
"""

from pathlib import Path
from typing import Annotated, Any

import typer

from minitest_cli.commands.draft_helpers import (
    EXIT_GENERAL_ERROR,
    EXIT_NOT_FOUND,
    DraftTarget,
    call,
    draft_path,
    resolve_target,
)
from minitest_cli.commands.draft_render import (
    ASK_TABLE_HEADERS,
    ask_fields,
    read_file,
    read_text,
    show_draft,
)
from minitest_cli.commands.run_helpers import ensure_uuid
from minitest_cli.utils.output import (
    print_error,
    print_info,
    print_json,
    print_success,
    print_table,
)

app = typer.Typer(
    name="ask", help="Read and answer Mini's questions on a draft.", no_args_is_help=True
)
DraftIdArg = Annotated[str, typer.Argument(help="Draft ID.")]
AskIdArg = Annotated[str, typer.Argument(help="Ask ID (from `draft ask list`).")]


def _open_asks(target: DraftTarget, draft_id: str) -> list[dict[str, Any]]:
    return call(target, "GET", draft_path(draft_id), retry=True).get("asks") or []


def _find_ask(target: DraftTarget, draft_id: str, ask_id: str) -> dict[str, Any]:
    ensure_uuid(ask_id, kind="ask id")
    for ask in _open_asks(target, draft_id):
        if ask.get("id") == ask_id:
            return ask
    print_error(f"No open ask {ask_id} on draft {draft_id}; see `minitest draft ask list`.")
    raise typer.Exit(code=EXIT_NOT_FOUND)


def _pair(raw: str, flag: str) -> tuple[str, str]:
    key, sep, value = raw.partition("=")
    if not sep or not key:
        print_error(f"{flag} expects KEY=VALUE.")
        raise typer.Exit(code=EXIT_GENERAL_ERROR)
    return key, value


def _fields(ask: dict[str, Any], inline: list[str], files: list[str]) -> dict[str, str]:
    known = {f["key"]: f for f in ask.get("answerFields") or []}
    values: dict[str, str] = {}
    for raw in inline:
        key, value = _pair(raw, "--field")
        if known.get(key, {}).get("secret"):
            print_error(f"'{key}' is secret: pass it with --field-file {key}=PATH (- = stdin).")
            raise typer.Exit(code=EXIT_GENERAL_ERROR)
        values[key] = value
    if sum(1 for raw in files if _pair(raw, "--field-file")[1] == "-") > 1:
        print_error("Only one --field-file can read stdin.")
        raise typer.Exit(code=EXIT_GENERAL_ERROR)
    for raw in files:
        key, path = _pair(raw, "--field-file")
        values[key] = read_file(Path(path)).removesuffix("\n")
    unknown = sorted(set(values) - set(known))
    if unknown:
        print_error(f"Unknown field(s) {', '.join(unknown)}; this ask takes: {ask_fields(ask)}.")
        raise typer.Exit(code=EXIT_GENERAL_ERROR)
    return values


@app.command(name="list")
def list_asks(draft_id: DraftIdArg) -> None:
    """List Mini's open questions on a draft, with the fields each answer takes."""
    target = resolve_target()
    asks = _open_asks(target, draft_id)
    if target.json_mode:
        print_json(asks)
        return
    if not asks:
        print_info("Mini is not asking anything.")
        return
    rows = [[a["id"], a.get("askType", "-"), a["question"], ask_fields(a)] for a in asks]
    print_table(ASK_TABLE_HEADERS, rows)


@app.command(name="answer")
def answer_ask(
    draft_id: DraftIdArg,
    ask_id: AskIdArg,
    answer: Annotated[str | None, typer.Option("--answer", help="Free-text answer.")] = None,
    answer_file: Annotated[
        Path | None, typer.Option("--answer-file", help="Read the answer from a file (- = stdin).")
    ] = None,
    field: Annotated[
        list[str] | None, typer.Option("--field", help="KEY=VALUE for a non-secret field.")
    ] = None,
    field_file: Annotated[
        list[str] | None,
        typer.Option("--field-file", help="KEY=PATH, value read from a file (- = stdin)."),
    ] = None,
) -> None:
    """Answer an ask; Mini resumes the draft with it. Turns auto-merge off."""
    text = read_text(answer, answer_file, flag="answer", required=False)
    target = resolve_target()
    ask = _find_ask(target, draft_id, ask_id)
    values = _fields(ask, field or [], field_file or [])
    if text is None and not values:
        print_error("Pass --answer/--answer-file, or the ask's fields with --field/--field-file.")
        raise typer.Exit(code=EXIT_GENERAL_ERROR)
    body: dict[str, object] = {}
    if text is not None:
        body["answer"] = text
    if values:
        body["fields"] = values
    draft = call(target, "POST", draft_path(draft_id, f"/asks/{ask_id}/answer"), json=body)
    print_success("Answered; Mini picks it up next.")
    show_draft(draft, json_mode=target.json_mode)


@app.command(name="decline")
def decline_ask(
    draft_id: DraftIdArg,
    ask_id: AskIdArg,
    reason: Annotated[str | None, typer.Option("--reason", help="Why, so Mini can adapt.")] = None,
) -> None:
    """Decline an ask; Mini carries on without it."""
    target = resolve_target()
    ensure_uuid(ask_id, kind="ask id")
    body = {"reason": reason} if reason else None
    draft = call(target, "POST", draft_path(draft_id, f"/asks/{ask_id}/decline"), json=body)
    print_success("Declined.")
    show_draft(draft, json_mode=target.json_mode)
