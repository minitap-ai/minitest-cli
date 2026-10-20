"""``minitest secret``: the app's Secrets vault. Values are write-only and never printed."""

from typing import Annotated, Any

import typer

from minitest_cli.commands import secret_extract, secret_lint, secret_manage
from minitest_cli.commands.secret_helpers import (
    CARD_FIELDS,
    EXIT_NOT_FOUND,
    JsonOption,
    KindOption,
    call,
    command_context,
    format_usage,
    reference,
    refuse_agent_context,
    secrets_path,
    validate_name,
)
from minitest_cli.commands.secret_value import read_secret_body
from minitest_cli.utils.output import (
    print_error,
    print_info,
    print_json,
    print_success,
    print_table,
)

app = typer.Typer(
    name="secret",
    help=(
        "Manage the app's secrets (passwords, OTP seeds, cards, API tokens). Reference them in "
        "scenarios and skills as {{secret:NAME}} (card fields: {{secret:NAME.number}}); the "
        "legacy $NAME still works but lint warns. Values are write-only and never printed."
    ),
    no_args_is_help=True,
)

NameArg = Annotated[str, typer.Argument(help="UPPER_SNAKE secret name, e.g. ADMIN_PASSWORD.")]


def fetch_vault(settings: Any, app_id: str) -> dict[str, Any]:
    return call(settings, "GET", secrets_path(app_id), collection=True) or {}


def _request_rows(requests: list[dict[str, Any]]) -> list[list[str]]:
    return [
        [
            r.get("name", ""),
            r.get("kind", ""),
            r.get("storyName") or r.get("storyId") or "",
            r.get("requestedBy", ""),
            r.get("reason", ""),
        ]
        for r in requests
    ]


@app.command(name="list")
def list_secrets(
    missing: Annotated[
        bool, typer.Option("--missing", help="Only show requested secrets that do not exist yet.")
    ] = False,
    json_flag: JsonOption = False,
) -> None:
    """List secrets (name, kind, note, version, usages) and open secret requests."""
    settings, json_mode, app_id = command_context(json_flag)
    vault = fetch_vault(settings, app_id)
    secrets: list[dict[str, Any]] = vault.get("secrets") or []
    requests: list[dict[str, Any]] = vault.get("requests") or []
    if json_mode:
        print_json(
            {"requests": requests} if missing else {"secrets": secrets, "requests": requests}
        )
        return
    if not missing:
        if secrets:
            rows = [
                [
                    s.get("name", ""),
                    s.get("kind", ""),
                    str(s.get("version", "")),
                    str(len(s.get("usages") or [])),
                    s.get("note") or "",
                ]
                for s in secrets
            ]
            print_table(["Name", "Kind", "Version", "Usages", "Note"], rows, title="Secrets")
        else:
            print_info("No secrets yet. Add one with: minitest secret set NAME --kind <kind>")
    if requests:
        headers = ["Name", "Kind", "Scenario", "Requested By", "Reason"]
        print_table(headers, _request_rows(requests), title="Requested (missing) secrets")
    elif missing:
        print_info("No missing secrets.")


@app.command(name="describe")
def describe_secret(name: NameArg, json_flag: JsonOption = False) -> None:
    """Show a secret's kind, note, usages and the reference to copy (never its value)."""
    settings, json_mode, app_id = command_context(json_flag)
    vault = fetch_vault(settings, app_id)
    found = next((s for s in vault.get("secrets") or [] if s.get("name") == name), None)
    requests = [r for r in vault.get("requests") or [] if r.get("name") == name]
    if found is None and not requests:
        print_error(f"No secret named {name}.")
        raise typer.Exit(code=EXIT_NOT_FOUND)
    fields = list(CARD_FIELDS) if found and found.get("kind") == "card" else []
    refs = [reference(name, f) for f in fields] or [reference(name)]
    if json_mode:
        print_json({"secret": found, "references": refs, "requests": requests})
        return
    if found is None:
        print(f"{name}: requested, not set yet")  # noqa: T201
        print_table(["Name", "Kind", "Scenario", "Requested By", "Reason"], _request_rows(requests))
        print_info(f"Set it with: minitest secret set {name} --kind {requests[0].get('kind')}")
        return
    for label, value in (
        ("Name", name),
        ("Kind", found.get("kind")),
        ("Note", found.get("note") or "-"),
        ("Version", found.get("version")),
        ("Updated", f"{found.get('updatedAt', '-')} by {found.get('updatedBy') or '-'}"),
        ("Reference", ", ".join(refs)),
    ):
        print(f"{label}: {value}")  # noqa: T201
    usages = found.get("usages") or []
    print(f"Usages: {len(usages)}")  # noqa: T201
    for usage in usages:
        print(f"  - {format_usage(usage)}")  # noqa: T201


@app.command(name="set")
def set_secret(
    name: NameArg,
    kind: KindOption,
    note: Annotated[str | None, typer.Option("--note", help="What this secret is for.")] = None,
    interactive: Annotated[bool, typer.Option("--interactive", hidden=True)] = False,
    json_flag: JsonOption = False,
) -> None:
    """Create or replace a secret. The value is read from stdin only.

    password/totp/token/text: the raw value, e.g. ``printf '%s' "$V" | minitest secret set X
    --kind token``. card: a JSON object, e.g. ``echo '{"number":"4242…","expiry":"12/34",
    "cvc":"123"}' | minitest secret set CARD --kind card`` (optional holder_name, postal_code).
    """
    refuse_agent_context()
    validate_name(name)
    settings, json_mode, app_id = command_context(json_flag)
    body: dict[str, Any] = {
        "kind": kind.value,
        **read_secret_body(name, kind, interactive=interactive),
    }
    if note is not None:
        body["note"] = note
    saved = call(settings, "PUT", f"{secrets_path(app_id)}/{name}", json=body) or {}
    if json_mode:
        print_json(saved)
        return
    print_success(
        f"Secret {name} saved (v{saved.get('version', '?')}). Reference: {reference(name)}"
    )


secret_manage.register(app)
secret_lint.register(app)
secret_extract.register(app)
