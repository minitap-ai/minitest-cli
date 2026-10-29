"""`minitest reference [TOPIC]`: the reference documents behind the agent skill."""

import difflib
import sys
from typing import Annotated, Any

import typer

from minitest_cli import __version__
from minitest_cli.commands.user_story_helpers import get_settings, is_json_mode
from minitest_cli.utils import reference_docs
from minitest_cli.utils.output import (
    print_error,
    print_info,
    print_json,
    print_table,
    print_warning,
)

EXIT_NOT_FOUND = 4

HELP = "Print one of the reference documents behind the agent skill. Omit TOPIC to list them."


def _warn_fallback(reason: str) -> None:
    print_warning(
        f"Minitest did not serve the reference ({reason}); "
        f"using the copy bundled with minitest-cli {__version__}."
    )


def _index() -> list[dict[str, Any]]:
    try:
        return reference_docs.fetch_index(get_settings())
    except reference_docs.ReferenceUnavailableError as exc:
        _warn_fallback(str(exc))
        return reference_docs.bundled_index()


def _document(topic: str) -> str:
    try:
        return reference_docs.fetch_topic(get_settings(), topic)
    except reference_docs.ReferenceUnavailableError as exc:
        _warn_fallback(str(exc))
        return reference_docs.bundled_topic(topic)


def _fail_unknown(error: reference_docs.UnknownTopicError) -> None:
    print_error(f"Unknown reference topic '{error.topic}'. Topics: {', '.join(error.topics)}.")
    suggestion = difflib.get_close_matches(error.topic, error.topics, n=1)
    if suggestion:
        print_info(f"Did you mean '{suggestion[0]}'? Run: minitest reference {suggestion[0]}")
    raise typer.Exit(EXIT_NOT_FOUND)


def reference(
    topic: Annotated[
        str | None, typer.Argument(help="Topic to print. Omit to list the topics.")
    ] = None,
) -> None:
    """Print a reference document as markdown, or list the topics.

    Read from Minitest so it is always current; when Minitest cannot be reached, the
    copy bundled with this CLI is printed instead. Diagnostics go to stderr.
    """
    if topic is None:
        index = _index()
        if is_json_mode():
            print_json(index)
            return
        print_table(
            ["TOPIC", "TITLE", "SUMMARY"],
            [[entry["topic"], entry["title"], entry["summary"]] for entry in index],
        )
        print_info("Print one with: minitest reference <topic>")
        return

    try:
        content = _document(topic)
    except reference_docs.UnknownTopicError as error:
        _fail_unknown(error)
        return
    if is_json_mode():
        print_json({"topic": topic, "content": content})
        return
    sys.stdout.write(content)
