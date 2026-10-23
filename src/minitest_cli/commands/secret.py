"""``minitest secret``: the app's Secrets vault. Values are write-only and never printed."""

from typing import Annotated, Any

import typer

from minitest_cli.commands import secret_create, secret_extract, secret_lint, secret_manage
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
from minitest_cli.commands.secret_state import has_value, request_rows, secret_rows, state
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


@app.command(name="list")
def list_secrets(
    missing: Annotated[
        bool, typer.Option("--missing", help="Only show secrets still waiting for a value.")
    ] = False,
    json_flag: JsonOption = False,
) -> None:
    """List secrets (name, kind, state, version, usages, note); those without a value first."""
    settings, json_mode, app_id = command_context(json_flag)
    vault = fetch_vault(settings, app_id)
    secrets: list[dict[str, Any]] = vault.get("secrets") or []
    requests: list[dict[str, Any]] = vault.get("requests") or []
    if missing:
        secrets = [s for s in secrets if not has_value(s)]
    if json_mode:
        print_json({"secrets": secrets, "requests": requests})
        return
    if secrets:
        headers = ["Name", "Kind", "State", "Version", "Usages", "Note"]
        print_table(headers, secret_rows(secrets), title="Secrets")
    elif not missing:
        print_info("No secrets yet. Add one with: minitest secret set NAME --kind <kind>")
    if requests:
        headers = ["Name", "Kind", "Scenario", "Requested By", "Reason"]
        print_table(headers, request_rows(requests), title="Requested (missing) secrets")
    elif missing and not secrets:
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
        print_table(["Name", "Kind", "Scenario", "Requested By", "Reason"], request_rows(requests))
        print_info(f"Set it with: minitest secret set {name} --kind {requests[0].get('kind')}")
        return
    lines = [("Name", name), ("Kind", found.get("kind")), ("State", state(found))]
    if not has_value(found):
        lines += [
            ("Requested by", found.get("requestedBy") or "-"),
            ("For scenario", found.get("requestedForUserStoryId") or "-"),
        ]
    else:
        lines += [
            ("Version", found.get("version")),
            ("Updated", f"{found.get('updatedAt', '-')} by {found.get('updatedBy') or '-'}"),
        ]
    lines += [("Note", found.get("note") or "-"), ("Reference", ", ".join(refs))]
    for label, value in lines:
        print(f"{label}: {value}")  # noqa: T201
    usages = found.get("usages") or []
    print(f"Usages: {len(usages)}")  # noqa: T201
    for usage in usages:
        print(f"  - {format_usage(usage)}")  # noqa: T201
    if not has_value(found):
        print_info(f"Set it with: minitest secret set {name} --kind {found.get('kind')}")


@app.command(name="set")
def set_secret(
    name: NameArg,
    kind: KindOption,
    note: Annotated[str | None, typer.Option("--note", help="What this secret is for.")] = None,
    interactive: Annotated[bool, typer.Option("--interactive", hidden=True)] = False,
    json_flag: JsonOption = False,
) -> None:
    """Create or replace a secret, or fill one waiting for a value. Value from stdin only.

    password, totp, token, text: the raw value, e.g.
    printf '%s' "$V" | minitest secret set X --kind token

    card: a JSON object (optional holder_name, postal_code), e.g.
    minitest secret set C --kind card <<< '{"number":"<number>","expiry":"<MM/YY>","cvc":"<cvc>"}'

    Without a value at hand, see secret create.
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


secret_create.register(app)
secret_manage.register(app)
secret_lint.register(app)
secret_extract.register(app)
