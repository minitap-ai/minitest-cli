"""``minitest issues ticket``: file an issue in the tenant's tracker, or link an existing ticket.

Same flow as the webapp's ticket form: pick a destination (``targets``), read the
properties it takes (``fields``), then ``create``; or ``search`` the tracker and ``link``.
The tracker must already be connected to the workspace (Settings > Integrations).
"""

from enum import StrEnum
from typing import Annotated, Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.run_helpers import (
    ensure_uuid,
    handle_response_error,
    resolve_app,
    run_api_call,
)
from minitest_cli.utils.output import print_error, print_json


class Provider(StrEnum):
    linear = "linear"
    jira = "jira"
    notion = "notion"
    github = "github"


app = typer.Typer(
    name="ticket",
    help="Create, link, read or unlink an issue's tracker ticket.",
    no_args_is_help=True,
)
IssueIdArg = Annotated[str, typer.Argument(help="Issue ID (the `id` from `issues list`).")]
ProviderArg = Annotated[Provider, typer.Argument(help="Tracker: linear, jira, notion or github.")]
ProviderOpt = Annotated[Provider, typer.Option("--provider", help="Tracker the ticket lives in.")]
TargetOpt = Annotated[
    str, typer.Option("--target", help="Destination id from `minitest issues ticket targets`.")
]


def _send(method: str, path: str, **kwargs: Any) -> None:
    """Send one request under the active app and print its JSON body."""
    settings, app_id, _ = resolve_app()

    async def _call() -> Any:
        async with ApiClient(settings) as client:
            resp = await client.request(method, f"/api/v1/apps/{app_id}{path}", **kwargs)
            handle_response_error(resp, resource="Ticket")
            return resp.json()

    print_json(run_api_call(_call()))


def _issue_path(issue_id: str, suffix: str = "") -> str:
    return f"/failures/{ensure_uuid(issue_id, kind='issue')}/ticket{suffix}"


def _fields(raw: list[str]) -> dict[str, list[str]]:
    fields: dict[str, list[str]] = {}
    for item in raw:
        key, sep, value = item.partition("=")
        if not sep or not key:
            print_error("--field expects KEY=VALUE.")
            raise typer.Exit(code=1)
        fields.setdefault(key, []).append(value)
    return fields


@app.command()
def targets(provider: ProviderArg) -> None:
    """List where tickets can be filed (teams, projects, databases, repositories)."""
    _send("GET", f"/trackers/{provider.value}/targets")


@app.command()
def fields(
    provider: ProviderArg,
    target: TargetOpt,
    issue_type: Annotated[
        str | None,
        typer.Option("--issue-type", help="Also list the optional properties of this issue type."),
    ] = None,
) -> None:
    """List the properties a destination takes, with their option ids."""
    if issue_type is None:
        _send("GET", f"/trackers/{provider.value}/fields", params={"target_id": target})
        return
    params = {"target_id": target, "issue_type": issue_type}
    _send("GET", f"/trackers/{provider.value}/fields/extra", params=params)


@app.command()
def search(
    provider: ProviderArg,
    query: Annotated[str, typer.Argument(help="Ticket key, URL or free text.")] = "",
    target: Annotated[
        str | None, typer.Option("--target", help="Only search this destination's site.")
    ] = None,
) -> None:
    """Search the tracker for an existing ticket to link."""
    params = {"q": query} | ({"target_id": target} if target else {})
    _send("GET", f"/trackers/{provider.value}/issues", params=params)


@app.command()
def create(
    issue_id: IssueIdArg,
    provider: ProviderOpt,
    target: TargetOpt,
    field: Annotated[
        list[str] | None,
        typer.Option("--field", help="KEY=VALUE (option id or text); repeat a key for several."),
    ] = None,
) -> None:
    """Create a ticket from an issue and link it."""
    body = {"provider": provider.value, "targetId": target, "fields": _fields(field or [])}
    _send("POST", _issue_path(issue_id), json=body)


@app.command()
def link(
    issue_id: IssueIdArg,
    provider: ProviderOpt,
    ticket: Annotated[str, typer.Option("--ticket", help="Ticket id or key from `search`.")],
) -> None:
    """Link an issue to a ticket that already exists."""
    body = {"provider": provider.value, "externalId": ticket}
    _send("POST", _issue_path(issue_id, "/link"), json=body)


@app.command()
def get(issue_id: IssueIdArg) -> None:
    """Show the issue's linked ticket and its live status in the tracker."""
    _send("GET", _issue_path(issue_id))


@app.command()
def unlink(issue_id: IssueIdArg) -> None:
    """Unlink the ticket from the issue; the ticket itself stays in the tracker."""
    _send("DELETE", _issue_path(issue_id))
