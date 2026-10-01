"""``app-skill secret set|list|unset``: write-only values exposed to Mini as env vars."""

import sys
from typing import Annotated, Any

import typer

from minitest_cli.commands.app_skill_helpers import call, command_context, skills_path
from minitest_cli.utils.output import (
    print_error,
    print_info,
    print_json,
    print_success,
    print_table,
)

app = typer.Typer(
    name="secret",
    help="Manage a skill's secrets. Values are write-only and never printed back.",
    no_args_is_help=True,
)

SkillArg = Annotated[str, typer.Argument(help="Skill name (or id).")]
SecretArg = Annotated[str, typer.Argument(help="UPPER_SNAKE env var name, e.g. TEST_API_KEY.")]


@app.command(name="set")
def set_secret(name: SkillArg, secret: SecretArg) -> None:
    """Set or replace a secret; the value is read from stdin."""
    settings, json_mode, app_id = command_context()
    if sys.stdin.isatty():
        print_error(f"Pipe the value of {secret} on stdin, e.g. printf '%s' \"$V\" | minitest …")
        raise typer.Exit(code=1)
    value = sys.stdin.read().rstrip("\r\n")
    if not value:
        print_error("Empty value: pipe the secret on stdin.")
        raise typer.Exit(code=1)
    saved = call(
        settings,
        "PUT",
        f"{skills_path(app_id)}/{name}/secrets",
        json={"name": secret, "value": value},
    )
    if json_mode:
        print_json(saved)
        return
    print_success(f"Secret {secret} saved on {name} (v{saved['version']}).")


@app.command(name="list")
def list_secrets(name: SkillArg) -> None:
    """List secret names (never values)."""
    settings, json_mode, app_id = command_context()
    secrets: list[dict[str, Any]] = call(settings, "GET", f"{skills_path(app_id)}/{name}/secrets")
    if json_mode:
        print_json(secrets)
        return
    if not secrets:
        print_info(f"No secrets on {name}.")
        return
    rows = [[s["name"], str(s["version"]), s["updatedAt"]] for s in secrets]
    print_table(["Name", "Version", "Updated At"], rows, title=f"Secrets of {name}")


@app.command(name="unset")
def unset_secret(name: SkillArg, secret: SecretArg) -> None:
    """Remove a secret."""
    settings, json_mode, app_id = command_context()
    call(settings, "DELETE", f"{skills_path(app_id)}/{name}/secrets/{secret}")
    if json_mode:
        print_json({"removed": secret})
        return
    print_success(f"Secret {secret} removed from {name}.")
