"""Shared plumbing for the ``app-skill`` command group."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.user_story_helpers import (
    extract_detail,
    get_app_flag,
    get_settings,
    is_json_mode,
    run_api_call,
)
from minitest_cli.core.app_context import resolve_app_id
from minitest_cli.core.auth import require_auth
from minitest_cli.core.config import Settings
from minitest_cli.utils.output import err_console, print_error, print_warning

EXIT_GENERAL_ERROR = 1
EXIT_NETWORK_ERROR = 3
EXIT_NOT_FOUND = 4
EXIT_LINKED = 6

SKILL_TABLE_HEADERS = ["Name", "Version", "Platforms", "Secrets", "Description"]

_NOT_ENABLED = "not enabled for this workspace"


def skills_path(app_id: str) -> str:
    return f"/api/v1/apps/{app_id}/skills"


def command_context() -> tuple[Settings, bool, str]:
    settings = get_settings()
    require_auth(settings)
    return settings, is_json_mode(), resolve_app_id(settings, get_app_flag())


def handle_skill_response(resp: httpx.Response) -> None:
    if resp.status_code < 400:
        return
    detail = extract_detail(resp) or f"API error: {resp.status_code}"
    if resp.status_code in (401, 403):
        print_error(f"Authentication failed ({resp.status_code}): {detail}")
        raise typer.Exit(code=EXIT_GENERAL_ERROR)
    if resp.status_code == 404 and _NOT_ENABLED in detail:
        print_error("Skills are not enabled for this workspace.")
        raise typer.Exit(code=EXIT_NOT_FOUND)
    if resp.status_code == 409 and _linked_scenarios(resp):
        _print_linked(_linked_scenarios(resp))
        raise typer.Exit(code=EXIT_LINKED)
    print_error(detail)
    raise typer.Exit(code=EXIT_NOT_FOUND if resp.status_code == 404 else EXIT_NETWORK_ERROR)


def _linked_scenarios(resp: httpx.Response) -> list[dict[str, Any]]:
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        return []
    if not isinstance(body, dict) or body.get("error") != "skill_linked":
        return []
    return [s for s in body.get("linkedScenarios") or [] if isinstance(s, dict)]


def _print_linked(scenarios: list[dict[str, Any]]) -> None:
    print_error(f"This skill is linked to {len(scenarios)} scenario(s):")
    for scenario in scenarios:
        err_console.print(f"  - {scenario.get('name', '')} ({scenario.get('id', '')})")
    err_console.print("Re-run with --unlink-scenarios --yes to unlink them and delete the skill.")


def call(
    settings: Settings,
    method: str,
    path: str,
    *,
    json: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> Any:
    async def _run() -> Any:
        async with ApiClient(settings) as client:
            resp = await client.request(method, path, json=json, params=params)
            handle_skill_response(resp)
            return resp.json() if resp.content else None

    return run_api_call(_run())


def read_instructions(instructions: str | None, instructions_file: Path | None) -> str | None:
    if instructions is not None and instructions_file is not None:
        print_error("Use either --instructions or --instructions-file, not both.")
        raise typer.Exit(code=1)
    if instructions_file is not None:
        return instructions_file.read_text(encoding="utf-8")
    return instructions


def warn_undefined_secrets(skill: dict[str, Any]) -> None:
    undefined = skill.get("undefinedSecrets") or []
    if undefined:
        names = ", ".join(f"${name}" for name in undefined)
        print_warning(
            f"Instructions use {names} but no such secret is defined. "
            f"Add it with: minitest app-skill secret set {skill.get('name')} <NAME>"
        )


def skill_row(skill: dict[str, Any]) -> list[str]:
    return [
        skill.get("name", ""),
        str(skill.get("version", "")),
        ", ".join(skill.get("platforms") or []) or "all",
        ", ".join(skill.get("secretNames") or []),
        skill.get("description", ""),
    ]
