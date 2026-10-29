"""Commands for reading app issues, their fix prompts, and triaging them."""

from enum import StrEnum
from typing import Annotated

import typer

from minitest_cli.commands.issues_fix import archive, fix, reopen
from minitest_cli.commands.issues_get import get
from minitest_cli.commands.issues_not_a_bug import not_a_bug
from minitest_cli.commands.issues_severity import severity
from minitest_cli.commands.issues_ticket import app as ticket_app
from minitest_cli.commands.issues_service import collect_issues
from minitest_cli.commands.run_helpers import ensure_uuid, resolve_app, run_api_call
from minitest_cli.utils.output import print_error, print_json


class IssuePlatform(StrEnum):
    ios = "ios"
    android = "android"
    web = "web"


class IssueCriticality(StrEnum):
    critical = "critical"
    warning = "warning"


app = typer.Typer(
    name="issues",
    help="Read app issues and their fix prompts, and triage them as in the webapp.",
    no_args_is_help=True,
)
app.command()(get)
app.command()(fix)
app.command(name="not-a-bug")(not_a_bug)
app.command()(archive)
app.command()(reopen)
app.command()(severity)
app.add_typer(ticket_app)


@app.command("list")
def list_issues(
    issue: Annotated[str | None, typer.Option("--issue", help="Scope to one issue ID.")] = None,
    run: Annotated[str | None, typer.Option("--run", help="Scope to one scenario run ID.")] = None,
    batch: Annotated[
        str | None, typer.Option("--batch", help="Scope to one run (batch) ID.")
    ] = None,
    all_runs: Annotated[
        bool,
        typer.Option(
            "--all-runs",
            help="Every issue of the app, whatever run it was last seen in (the Issues page).",
        ),
    ] = False,
    platform: Annotated[
        IssuePlatform | None, typer.Option(help="Filter by execution platform.")
    ] = None,
    criticality: Annotated[
        IssueCriticality | None, typer.Option(help="Filter by issue criticality.")
    ] = None,
    include_resolved: Annotated[
        bool, typer.Option("--include-resolved", help="Include resolved issues.")
    ] = False,
) -> None:
    """Return scoped issues, build provenance, fix prompts, and deeplinks as JSON."""
    scopes = {"issue": issue, "run": run, "batch": batch}
    selected = [(kind, value) for kind, value in scopes.items() if value is not None]
    if len(selected) + int(all_runs) > 1:
        print_error("Choose only one scope: --issue, --run, --batch, or --all-runs.")
        raise typer.Exit(1)
    for kind, value in selected:
        ensure_uuid(value, kind=kind)

    settings, app_id, _ = resolve_app()
    result = run_api_call(
        collect_issues(
            settings,
            app_id,
            issue_id=issue,
            story_run_id=run,
            batch_id=batch,
            all_runs=all_runs,
            platform=platform.value if platform is not None else None,
            criticality=criticality.value if criticality is not None else None,
            include_resolved=include_resolved,
        )
    )
    print_json(result.model_dump(mode="json", by_alias=True))
