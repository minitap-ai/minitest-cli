"""Confirmation gate shared by destructive commands."""

import typer

from minitest_cli.utils.output import print_error

EXIT_GENERAL_ERROR = 1


def confirm_or_exit(yes: bool, action: str) -> None:
    """Gate a mutating action behind explicit confirmation.

    Passing ``--yes`` proceeds. Without it we refuse rather than prompt, so the
    command stays safe to run non-interactively (agents/CI) — exit 1 naming the
    flag that unblocks it.
    """
    if yes:
        return
    print_error(f"{action} requires confirmation. Re-run with --yes to proceed.")
    raise typer.Exit(code=EXIT_GENERAL_ERROR)
