"""``app-skill``: procedures Mini follows to arrange test state for an app.

A skill is how to reach a state the app under test can't put itself in:
a customer test backend, an admin console, a debug menu, a sandbox payment.
"""

from typing import Annotated, Any

import typer

from minitest_cli.commands import app_skill_secret, app_skill_write
from minitest_cli.commands.app_skill_helpers import (
    SKILL_TABLE_HEADERS,
    call,
    command_context,
    skill_row,
    skills_path,
    warn_undefined_secrets,
)
from minitest_cli.utils.output import print_info, print_json, print_success, print_table

app = typer.Typer(
    name="app-skill",
    help="Manage app skills (Skills in the webapp): procedures Mini loads to arrange test state.",
    no_args_is_help=True,
)
app.add_typer(app_skill_secret.app)
app_skill_write.register(app)

SkillArg = Annotated[str, typer.Argument(help="Skill name (or id).")]


@app.command(name="list")
def list_skills() -> None:
    """List the live skills of the app."""
    settings, json_mode, app_id = command_context()
    data = call(settings, "GET", skills_path(app_id))
    items: list[dict[str, Any]] = data.get("items", [])
    if json_mode:
        print_json(data)
        return
    if not items:
        print_info("No skills for this app.")
        return
    print_table(SKILL_TABLE_HEADERS, [skill_row(s) for s in items], title=f"Skills ({len(items)})")


@app.command(name="get")
def get_skill(name: SkillArg) -> None:
    """Print a skill: description, platforms, secrets, instructions, open proposal."""
    settings, json_mode, app_id = command_context()
    skill = call(settings, "GET", f"{skills_path(app_id)}/{name}")
    warn_undefined_secrets(skill)
    if json_mode:
        print_json(skill)
        return
    print(f"# {skill['name']} (v{skill['version']})")  # noqa: T201
    print(f"Use when: {skill['description']}")  # noqa: T201
    print(f"Platforms: {', '.join(skill.get('platforms') or []) or 'all'}")  # noqa: T201
    print(f"Secrets: {', '.join(skill.get('secretNames') or []) or 'none'}")  # noqa: T201
    print()  # noqa: T201
    print(skill["instructions"])  # noqa: T201
    proposal = skill.get("openProposal")
    if proposal:
        print_info(f"Open maintenance proposal on v{proposal['baseVersion']}: {proposal['reason']}")


@app.command(name="delete")
def delete_skill(
    name: SkillArg,
    unlink_scenarios: Annotated[
        bool,
        typer.Option("--unlink-scenarios", help="Also unlink the scenarios that load it."),
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Confirm unlinking scenarios.")] = False,
) -> None:
    """Delete a skill. Its history stays readable with `history`."""
    settings, json_mode, app_id = command_context()
    if unlink_scenarios and not yes:
        print_info("Unlinking scenarios needs --yes.")
        raise typer.Exit(code=1)
    params = {"unlinkScenarios": "true"} if unlink_scenarios else None
    call(settings, "DELETE", f"{skills_path(app_id)}/{name}", params=params)
    if json_mode:
        print_json({"deleted": name})
        return
    print_success(f"Skill {name} deleted.")


@app.command(name="history")
def skill_history(name: SkillArg) -> None:
    """Show every version and change of a skill, including deleted ones (pass the id)."""
    settings, json_mode, app_id = command_context()
    history = call(settings, "GET", f"{skills_path(app_id)}/{name}/history")
    if json_mode:
        print_json(history)
        return
    rows = [_version_row(v) for v in history.get("versions", [])]
    rows += [_event_row(e) for e in history.get("events", [])]
    rows.sort(key=lambda row: row[0], reverse=True)
    print_table(["When", "Change", "Actor", "Channel"], rows, title=f"History of {history['name']}")


@app.command(name="restore")
def restore_skill(
    name: SkillArg,
    version: Annotated[int, typer.Option("--version", min=1, help="Version to restore.")],
) -> None:
    """Make an older version current again (as a new version)."""
    settings, json_mode, app_id = command_context()
    skill = call(
        settings, "POST", f"{skills_path(app_id)}/{name}/restore", json={"version": version}
    )
    if json_mode:
        print_json(skill)
        return
    print_success(f"Skill {skill['name']} restored from v{version} as v{skill['version']}.")


def _actor(entry: dict[str, Any]) -> str:
    kind = entry.get("actorKind") or ""
    if kind == "agent":
        return f"Mini ({entry.get('conversationId') or 'session'})"
    return entry.get("actorId") or kind


def _version_row(version: dict[str, Any]) -> list[str]:
    change = f"v{version['versionNumber']} {version['source']}"
    return [version["createdAt"], change, _actor(version), version.get("actorChannel") or ""]


def _event_row(event: dict[str, Any]) -> list[str]:
    detail = ", ".join(f"{k}={v}" for k, v in (event.get("detail") or {}).items())
    change = f"{event['event']} {detail}".strip()
    return [event["createdAt"], change, _actor(event), event.get("actorChannel") or ""]
