"""Human rendering and input reading for `minitest draft` (JSON mode prints the API body)."""

import sys
from pathlib import Path
from typing import Any

import typer

from minitest_cli.utils.output import print_error, print_json, print_table

EXIT_GENERAL_ERROR = 1

DRAFT_TABLE_HEADERS = ["ID", "Title", "State", "Reason", "Mini", "Auto check", "Auto merge"]
MESSAGE_TABLE_HEADERS = ["When", "Role", "Message"]
ASK_TABLE_HEADERS = ["Ask ID", "Type", "Question", "Fields"]
_SUMMARY_KEYS = (
    "id",
    "title",
    "state",
    "stateReason",
    "stateReasonCode",
    "miniWriting",
    "needsUser",
    "autoCheck",
    "autoMerge",
    "sessionId",
    "draftFeatureId",
    "lastActivityAt",
    "mergedAt",
)


def _display(value: Any) -> str:
    return "-" if value is None else str(value)


def mini_status(draft: dict[str, Any]) -> str:
    if draft.get("miniWriting"):
        return "writing"
    if draft.get("stateReasonCode") == "queued":
        return "queued"
    return "idle"


def draft_row(draft: dict[str, Any]) -> list[str]:
    return [
        _display(draft.get("id")),
        _display(draft.get("title")),
        _display(draft.get("state")),
        _display(draft.get("stateReason")),
        mini_status(draft),
        _display(draft.get("autoCheck")),
        _display(draft.get("autoMerge")),
    ]


def ask_fields(ask: dict[str, Any]) -> str:
    fields = ask.get("answerFields") or []
    return ", ".join(f"{f['key']}{' (secret)' if f.get('secret') else ''}" for f in fields) or "-"


def show_draft(draft: dict[str, Any], *, json_mode: bool) -> None:
    if json_mode:
        print_json(draft)
        return
    for key in _SUMMARY_KEYS:
        if key in draft:
            print(f"{key}: {_display(draft[key])}")  # noqa: T201
    linked = draft.get("linkedPr")
    if linked:
        print(f"linkedPr: {linked.get('repo') or ''}#{linked.get('number')}")  # noqa: T201
    stories = draft.get("stories")
    if stories:
        print(f"stories: {len(stories)}")  # noqa: T201
    asks = draft.get("asks")
    if asks:
        print_table(
            ASK_TABLE_HEADERS,
            [[a["id"], a.get("askType", "-"), a["question"], ask_fields(a)] for a in asks],
            title="Open asks — answer with `minitest draft ask answer`",
        )


def read_text(value: str | None, path: Path | None, *, flag: str, required: bool) -> str | None:
    """Return the text of exactly one of ``--{flag}`` / ``--{flag}-file`` (``-`` is stdin)."""
    if value is not None and path is not None:
        print_error(f"Use either --{flag} or --{flag}-file, not both.")
        raise typer.Exit(code=EXIT_GENERAL_ERROR)
    if path is not None:
        text = read_file(path)
    else:
        text = value
    if text is not None and not text.strip():
        print_error(f"--{flag} is empty.")
        raise typer.Exit(code=EXIT_GENERAL_ERROR)
    if text is None and required:
        print_error(f"Pass --{flag} TEXT or --{flag}-file PATH (use - for stdin).")
        raise typer.Exit(code=EXIT_GENERAL_ERROR)
    return text


def read_file(path: Path) -> str:
    """Read a UTF-8 file, or stdin for ``-``; never echoes what it read."""
    try:
        if str(path) == "-":
            return sys.stdin.read()
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print_error(f"Could not read '{path}': {exc.__class__.__name__}")
        raise typer.Exit(code=EXIT_GENERAL_ERROR) from exc
