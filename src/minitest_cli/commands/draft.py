"""`minitest draft`: ask Mini for a suite change and drive it to merge.

A draft is the workbench the webapp shows under Drafts: a branch of the suite plus
Mini's conversation about it. Mini is the only author of the branch; never `df apply`
into a draft's branch yourself.
"""

from typing import Annotated

import typer

from minitest_cli.commands import (
    draft_asks,
    draft_conversation,
    draft_create,
    draft_legacy,
    draft_lifecycle,
    draft_pr,
    draft_update,
)
from minitest_cli.commands.draft_helpers import (
    DRAFTS_PATH,
    call,
    draft_path,
    resolve_target,
    run_conductor,
)
from minitest_cli.commands.draft_render import (
    DRAFT_TABLE_HEADERS,
    draft_row,
    show_draft,
)
from minitest_cli.commands.draft_watch import WatchUntil, watch
from minitest_cli.utils.output import (
    print_info,
    print_json,
    print_table,
)

app = typer.Typer(
    name="draft",
    help="Ask Mini for a suite change, follow the conversation, and check/merge the result.",
    no_args_is_help=True,
)
EXIT_WATCH_TIMEOUT = 1


@app.command(name="list")
def list_drafts(
    history: Annotated[
        bool, typer.Option("--history", help="List merged and discarded drafts instead.")
    ] = False,
) -> None:
    """List the active app's drafts (open ones by default)."""
    target = resolve_target()
    params = {"appId": target.app_id, "scope": "history" if history else "open"}
    body = call(target, "GET", DRAFTS_PATH, retry=True, params=params)
    drafts = body.get("drafts", [])
    if target.json_mode:
        print_json(drafts)
        return
    if not drafts:
        print_info("No drafts found.")
        return
    print_table(
        DRAFT_TABLE_HEADERS, [draft_row(d) for d in drafts], title=f"Drafts ({len(drafts)})"
    )


@app.command(name="get")
def get_draft(
    draft_id: Annotated[str, typer.Argument(help="Draft ID.")],
    watch_flag: Annotated[
        bool, typer.Option("--watch", help="Poll until the draft is stable, then print it.")
    ] = False,
    until: Annotated[
        WatchUntil,
        typer.Option(
            "--until",
            help="idle: Mini has nothing queued. settled: also no check running.",
        ),
    ] = WatchUntil.IDLE,
    interval: Annotated[
        float, typer.Option("--interval", min=1.0, help="Seconds between polls.")
    ] = 5.0,
    timeout: Annotated[
        float, typer.Option("--timeout", min=1.0, help="Give up after this many seconds (exit 1).")
    ] = 900.0,
) -> None:
    """Show a draft: state, Mini's status, scenarios and open asks."""
    target = resolve_target()
    path = draft_path(draft_id)
    if not watch_flag:
        show_draft(call(target, "GET", path, retry=True), json_mode=target.json_mode)
        return
    draft, stable = run_conductor(
        watch(target, path, until=until, interval=interval, timeout=timeout)
    )
    show_draft(draft, json_mode=target.json_mode)
    if not stable:
        print_info(f"Still not {until.value} after {timeout:.0f}s; run the same command again.")
        raise typer.Exit(code=EXIT_WATCH_TIMEOUT)


draft_create.register(app)
draft_update.register(app)
draft_conversation.register(app)
draft_lifecycle.register(app)
draft_pr.register(app)
app.add_typer(draft_asks.app)
draft_legacy.register(app)
