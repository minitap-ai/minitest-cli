"""Commands for reading app findings, their fix prompts, and closing them."""

from enum import StrEnum
from typing import Annotated

import typer

from minitest_cli.commands.issues_fix import fix
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
    name="issues", help="Read app findings, fix prompts, and mark them fixed.", no_args_is_help=True
)
app.command()(fix)


@app.command("list")
def list_issues(
    issue: Annotated[str | None, typer.Option("--issue", help="Scope to one failure ID.")] = None,
    run: Annotated[str | None, typer.Option("--run", help="Scope to one story run ID.")] = None,
    batch: Annotated[str | None, typer.Option("--batch", help="Scope to one batch ID.")] = None,
    platform: Annotated[
        IssuePlatform | None, typer.Option(help="Filter by execution platform.")
    ] = None,
    criticality: Annotated[
        IssueCriticality | None, typer.Option(help="Filter by finding criticality.")
    ] = None,
    include_resolved: Annotated[
        bool, typer.Option("--include-resolved", help="Include resolved findings.")
    ] = False,
) -> None:
    """Return scoped findings, build provenance, fix prompts, and deeplinks as JSON."""
    scopes = {"issue": issue, "run": run, "batch": batch}
    selected = [(kind, value) for kind, value in scopes.items() if value is not None]
    if len(selected) > 1:
        print_error("Choose only one scope: --issue, --run, or --batch.")
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
            platform=platform.value if platform is not None else None,
            criticality=criticality.value if criticality is not None else None,
            include_resolved=include_resolved,
        )
    )
    print_json(result.model_dump(mode="json", by_alias=True))
