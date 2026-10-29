"""`minitest run ask list|get|answer|decline|approve|reject`: answer what Mini asked on a run.

While a run executes, Mini can get stuck on something only a person can settle (an
account to use, an expected behavior, a dependency to provide). It asks, the blocked
scenario runs show ``escalated``, and they resume once the question is answered.
"""

import textwrap
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console

from minitest_cli.commands.draft_render import read_text
from minitest_cli.commands.run_asks_helpers import (
    ask_path,
    call,
    get_escalation,
    has_pending_proposal,
    is_waiting,
    list_escalations,
)
from minitest_cli.commands.run_helpers import get_settings, is_json_mode
from minitest_cli.core.auth import require_auth
from minitest_cli.core.config import Settings
from minitest_cli.utils.output import (
    print_error,
    print_info,
    print_json,
    print_success,
)

app = typer.Typer(
    name="ask", help="Read and answer the questions Mini asks during a run.", no_args_is_help=True
)
AskIdArg = Annotated[str, typer.Argument(help="Question ID (from `minitest run ask list`).")]
ReasonOpt = Annotated[str | None, typer.Option("--reason", help="Why, so Mini can adapt.")]


def _settings() -> Settings:
    settings = get_settings()
    require_auth(settings)
    return settings


def _question(escalation: dict[str, Any]) -> str:
    diagnosis = escalation.get("diagnosis") or {}
    return escalation.get("question") or diagnosis.get("summary") or "-"


def _state(escalation: dict[str, Any]) -> str:
    if is_waiting(escalation):
        return "waiting for you"
    return str(escalation.get("state", "-"))


def _show(escalation: dict[str, Any]) -> None:
    if is_json_mode():
        print_json(escalation)
        return
    console = Console()
    console.print(f"[bold]Question {escalation['id']}[/bold] — {_state(escalation)}")
    width = max(console.width - 2, 40)
    proposed_fix = (escalation.get("diagnosis") or {}).get("proposedFix")
    lines = [_question(escalation)] + ([f"Mini proposes: {proposed_fix}"] if proposed_fix else [])
    for line in lines:
        console.print(textwrap.indent(textwrap.fill(line, width), "  "), markup=False)
    if has_pending_proposal(escalation):
        print_info("  Approve or reject it: `minitest run ask approve|reject <ask-id>`.")


@app.command(name="list")
def list_asks(
    batch_id: Annotated[str, typer.Argument(help="Run (batch) ID, the id in /test/runs/<id>.")],
    all_asks: Annotated[
        bool, typer.Option("--all", help="Also list answered, closed and Minitap-side questions.")
    ] = False,
) -> None:
    """List the questions Mini asked on a run; by default only those waiting for you."""
    escalations = list_escalations(_settings(), batch_id)
    if not all_asks:
        escalations = [e for e in escalations if is_waiting(e)]
    if is_json_mode():
        print_json(escalations)
        return
    if not escalations:
        print_info("Mini is not waiting on any answer for this run.")
        return
    console = Console(soft_wrap=False)
    for e in escalations:
        platforms = ", ".join(e.get("affectedPlatforms") or []) or "-"
        console.print(f"[bold]{e['id']}[/bold]  {_state(e)} · {platforms}", soft_wrap=True)
        wrapped = textwrap.fill(_question(e), width=max(console.width - 2, 40))
        console.print(textwrap.indent(wrapped, "  ") + "\n", markup=False, highlight=False)
    print_info(
        f"{len(escalations)} question(s). Answer: `minitest run ask answer <ask-id> --answer ...`."
    )


@app.command(name="get")
def get_ask(ask_id: AskIdArg) -> None:
    """Show one question with Mini's diagnosis and any proposed fix."""
    _show(get_escalation(_settings(), ask_id))


@app.command(name="answer")
def answer_ask(
    ask_id: AskIdArg,
    answer: Annotated[str | None, typer.Option("--answer", help="Free-text answer.")] = None,
    answer_file: Annotated[
        Path | None, typer.Option("--answer-file", help="Read the answer from a file (- = stdin).")
    ] = None,
) -> None:
    """Answer a question; Mini resumes the blocked scenario runs with it."""
    text = read_text(answer, answer_file, flag="answer", required=True)
    settings = _settings()
    escalation = get_escalation(settings, ask_id)
    if escalation.get("answerType") == "file":
        print_error("Mini asked for a file here; upload it from the run page in the webapp.")
        raise typer.Exit(code=1)
    call(
        settings,
        "POST",
        ask_path(ask_id, "/answer"),
        json={"answer": text, "answeredVia": "webapp"},
    )
    print_success("Answered; Mini picks it up next.")
    _show(get_escalation(settings, ask_id))


@app.command(name="decline")
def decline_ask(ask_id: AskIdArg, reason: ReasonOpt = None) -> None:
    """Decline a question; nobody will answer it and the blocked scenario runs close."""
    settings = _settings()
    call(settings, "POST", ask_path(ask_id, "/decline"), json={"reason": reason})
    print_success("Declined.")
    _show(get_escalation(settings, ask_id))


@app.command(name="approve")
def approve_ask(ask_id: AskIdArg) -> None:
    """Approve the fix Mini proposed for this question."""
    settings = _settings()
    call(settings, "POST", ask_path(ask_id, "/proposal/approve"))
    print_success("Approved; Mini applies it.")
    _show(get_escalation(settings, ask_id))


@app.command(name="reject")
def reject_ask(ask_id: AskIdArg, reason: ReasonOpt = None) -> None:
    """Reject the fix Mini proposed for this question."""
    settings = _settings()
    call(settings, "POST", ask_path(ask_id, "/proposal/reject"), json={"reason": reason})
    print_success("Rejected.")
    _show(get_escalation(settings, ask_id))
