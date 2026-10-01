"""``app-skill create|update|propose``."""

from pathlib import Path
from typing import Annotated, Any

import typer

from minitest_cli.commands.app_skill_helpers import (
    call,
    command_context,
    read_instructions,
    skills_path,
    warn_undefined_secrets,
)
from minitest_cli.utils.output import print_error, print_json, print_success

Description = Annotated[
    str | None,
    typer.Option("--description", help="One sentence: when Mini should use this skill."),
]
Platforms = Annotated[
    list[str] | None,
    typer.Option("--platform", help="ios, android or web (repeatable). Omit for all."),
]
Instructions = Annotated[
    str | None, typer.Option("--instructions", help="Markdown procedure Mini follows.")
]
InstructionsFile = Annotated[
    Path | None,
    typer.Option(
        "--instructions-file", exists=True, readable=True, dir_okay=False, help="Markdown file."
    ),
]
AllPlatforms = Annotated[
    bool, typer.Option("--all-platforms", help="Make the skill apply to every platform.")
]


def _patch(
    description: str | None,
    platforms: list[str] | None,
    all_platforms: bool,
    instructions: str | None,
    instructions_file: Path | None,
) -> dict[str, Any]:
    if platforms and all_platforms:
        print_error("Use either --platform or --all-platforms, not both.")
        raise typer.Exit(code=1)
    patch: dict[str, Any] = {}
    if description is not None:
        patch["description"] = description
    if platforms:
        patch["platforms"] = platforms
    if all_platforms:
        patch["platforms"] = []
    body = read_instructions(instructions, instructions_file)
    if body is not None:
        patch["instructions"] = body
    return patch


def _report(skill: dict[str, Any], json_mode: bool, message: str) -> None:
    warn_undefined_secrets(skill)
    if json_mode:
        print_json(skill)
        return
    print_success(message)


def register(app: typer.Typer) -> None:
    @app.command(name="create")
    def create_skill(
        name: Annotated[str, typer.Argument(help="kebab-case name, e.g. clutch-test-backend.")],
        description: Description = None,
        platforms: Platforms = None,
        instructions: Instructions = None,
        instructions_file: InstructionsFile = None,
    ) -> None:
        """Create a skill. Reference secrets as $NAME and set them with `secret set`."""
        settings, json_mode, app_id = command_context()
        body = _patch(description, platforms, False, instructions, instructions_file)
        if "description" not in body or "instructions" not in body:
            print_error("Provide --description and --instructions (or --instructions-file).")
            raise typer.Exit(code=1)
        skill = call(settings, "POST", skills_path(app_id), json={"name": name, **body})
        _report(skill, json_mode, f"Skill {skill['name']} created (v{skill['version']}).")

    @app.command(name="update")
    def update_skill(
        name: Annotated[str, typer.Argument(help="Skill name (or id).")],
        new_name: Annotated[str | None, typer.Option("--name", help="Rename the skill.")] = None,
        description: Description = None,
        platforms: Platforms = None,
        all_platforms: AllPlatforms = False,
        instructions: Instructions = None,
        instructions_file: InstructionsFile = None,
    ) -> None:
        """Change a skill; every change becomes a new version."""
        settings, json_mode, app_id = command_context()
        body = _patch(description, platforms, all_platforms, instructions, instructions_file)
        if new_name is not None:
            body["name"] = new_name
        if not body:
            print_error("Nothing to update.")
            raise typer.Exit(code=1)
        skill = call(settings, "PATCH", f"{skills_path(app_id)}/{name}", json=body)
        _report(skill, json_mode, f"Skill {skill['name']} is now v{skill['version']}.")

    @app.command(name="propose")
    def propose_update(
        name: Annotated[str, typer.Argument(help="Skill name (or id).")],
        reason: Annotated[
            str, typer.Option("--reason", help="What failed and why this update fixes it.")
        ],
        description: Description = None,
        platforms: Platforms = None,
        all_platforms: AllPlatforms = False,
        instructions: Instructions = None,
        instructions_file: InstructionsFile = None,
    ) -> None:
        """Propose an update a human accepts or dismisses (replaces any open proposal)."""
        settings, json_mode, app_id = command_context()
        body = _patch(description, platforms, all_platforms, instructions, instructions_file)
        if not body:
            print_error("Propose at least one change.")
            raise typer.Exit(code=1)
        proposal = call(
            settings,
            "POST",
            f"{skills_path(app_id)}/{name}/proposals",
            json={**body, "reason": reason},
        )
        if json_mode:
            print_json(proposal)
            return
        print_success(f"Update proposed for {name}; a member accepts or dismisses it.")
