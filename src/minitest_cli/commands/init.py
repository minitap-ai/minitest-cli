import os
import sys

import typer
from rich.console import Console
from rich.markdown import Markdown

from minitest_cli.commands.init_playbook import PLAYBOOK
from minitest_cli.utils.output import err_console, print_json

app = typer.Typer(name="init", help="Print the onboarding plan for an AI coding agent.")

_AGENT_ENV_VARS = (
    "CLAUDECODE",
    "CLAUDE_CODE",
    "CURSOR_TRACE_ID",
    "CURSOR_AGENT",
    "GEMINI_CLI",
    "OPENCODE",
    "CODEX_SANDBOX",
    "AIDER_CHAT",
    "REPLIT_AGENT",
    "WINDSURF_AGENT",
    "CLINE_ACTIVE",
    "GITHUB_COPILOT_AGENT",
)

_HUMAN_INTRO = (
    "`minitest init` writes the onboarding plan your AI coding agent runs. "
    "Paste the prompt below into Cursor / Claude Code / your agent, in your app's repo:"
)
_HUMAN_FOOTER = "Tip: the agent will start with [bold]minitest auth login[/bold]."


def _is_agent_context(*, agent_flag: bool, json_mode: bool) -> bool:
    if agent_flag or json_mode:
        return True
    if any(os.environ.get(var) for var in _AGENT_ENV_VARS):
        return True
    return not sys.stdout.isatty()


@app.callback(invoke_without_command=True)
def init(
    ctx: typer.Context,
    agent: bool = typer.Option(
        False,
        "--agent",
        help="Force raw playbook output for an AI agent (no decoration).",
    ),
) -> None:
    """Print the Minitest onboarding playbook.

    In an agent or non-interactive context, prints the raw markdown playbook to
    stdout. In an interactive terminal, renders it nicely with a short intro.
    """
    if ctx.invoked_subcommand is not None:
        return

    json_mode = bool(getattr(typer.Context, "json_mode", False))

    if json_mode:
        print_json({"playbook": PLAYBOOK})
        return

    if _is_agent_context(agent_flag=agent, json_mode=False):
        sys.stdout.write(PLAYBOOK)
        return

    err_console.print(_HUMAN_INTRO)
    Console().print(Markdown(PLAYBOOK))
    err_console.print(_HUMAN_FOOTER)
