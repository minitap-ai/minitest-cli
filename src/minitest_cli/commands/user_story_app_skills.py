from typing import Annotated, Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.app_skill_helpers import handle_skill_response
from minitest_cli.commands.user_story_helpers import (
    base_path,
    get_app_flag,
    get_settings,
    is_json_mode,
    run_api_call,
)
from minitest_cli.core.app_context import resolve_app_id
from minitest_cli.core.auth import require_auth
from minitest_cli.utils.output import output, print_error, print_success


def set_app_skills(
    user_story_id: Annotated[str, typer.Argument(help="Scenario ID.")],
    skill_names: Annotated[
        list[str] | None,
        typer.Option("--skill", help="App-skill name Mini loads before starting (repeatable)."),
    ] = None,
    clear: Annotated[bool, typer.Option("--clear", help="Unlink every app skill.")] = False,
) -> None:
    """Link app skills (see `minitest app-skill`) to a scenario, replacing the current ones."""
    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)
    app_id = resolve_app_id(settings, get_app_flag())

    if clear == bool(skill_names):
        print_error("Provide at least one --skill <name> or --clear.")
        raise typer.Exit(code=1)

    async def _run() -> dict[str, Any]:
        async with ApiClient(settings) as client:
            resp = await client.put(
                f"{base_path(app_id)}/{user_story_id}/skills",
                json={"skillNames": list(skill_names or [])},
            )
            handle_skill_response(resp)
            return resp.json()

    data = run_api_call(_run())
    if json_mode:
        output(data, json_mode=True)
        return
    names = ", ".join(s["name"] for s in data.get("skills", []))
    print_success(f"App skills linked to {user_story_id}: {names or 'none'}.")
