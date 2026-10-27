"""'apps backend-api': the backend Mini reads an OpenAPI document of and calls during runs."""

from typing import Annotated, Any

import typer

from minitest_cli.commands.app_network_helpers import call_api, fail, is_json_mode, resolve_target
from minitest_cli.core.config import Settings
from minitest_cli.commands.app_skill_helpers import skills_path
from minitest_cli.commands.backend_api_helpers import merge_secret_names, render_config
from minitest_cli.utils.output import print_success

app = typer.Typer(
    name="backend-api",
    help=(
        "Backend API of the app (--app): during runs Mini searches its OpenAPI document and "
        "calls it, authenticated with app vault secrets. Off by default."
    ),
    no_args_is_help=True,
)


def _path(app_id: str) -> str:
    return f"/api/v1/apps/{app_id}/backend-config"


def _call(
    settings: Settings, method: str, path: str, body: dict[str, Any] | None = None
) -> dict[str, Any]:
    return call_api(settings, method, path, body, forbidden="You cannot access this app.")


@app.command(name="show")
def show() -> None:
    """Show the app's backend API settings."""
    settings, app_id = resolve_target()
    render_config(_call(settings, "GET", _path(app_id)))


@app.command(name="set")
def set_config(
    enable: Annotated[
        bool | None,
        typer.Option(
            "--enable/--disable",
            help="Switch it on or off. On needs a base URL and an OpenAPI URL.",
        ),
    ] = None,
    base_url: Annotated[
        str | None,
        typer.Option("--base-url", help="Base URL Mini calls, e.g. https://api.staging.example."),
    ] = None,
    openapi_url: Annotated[
        str | None,
        typer.Option("--openapi-url", help="URL of the OpenAPI (or Swagger) document."),
    ] = None,
    secret: Annotated[
        list[str] | None,
        typer.Option(
            "--secret",
            help="App vault secret Mini authenticates calls with (repeatable), e.g. API_TOKEN.",
        ),
    ] = None,
    remove_secret: Annotated[
        list[str] | None,
        typer.Option("--remove-secret", help="Authentication secret to drop (repeatable)."),
    ] = None,
    clear_secrets: Annotated[
        bool,
        typer.Option("--clear-secrets", help="Drop every current secret before adding --secret."),
    ] = False,
    skill: Annotated[
        str | None,
        typer.Option("--skill", help="App skill (name or id) explaining how to use the backend."),
    ] = None,
    clear_skill: Annotated[
        bool, typer.Option("--clear-skill", help="Stop pointing Mini at a skill.")
    ] = False,
) -> None:
    """Change the app's backend API settings; options not passed stay as they are."""
    if skill and clear_skill:
        raise fail("Pass either --skill or --clear-skill, not both.")
    changes = [enable is not None, base_url, openapi_url, secret, remove_secret, clear_secrets]
    if not any([*changes, skill, clear_skill]):
        raise fail(
            "Nothing to change: pass --enable/--disable, --base-url, --openapi-url, "
            "a secret option or a skill option."
        )
    settings, app_id = resolve_target()
    current = _call(settings, "GET", _path(app_id))
    body: dict[str, Any] = {
        "enabled": current["enabled"] if enable is None else enable,
        "baseUrl": current["baseUrl"] if base_url is None else base_url,
        "openapiUrl": current["openapiUrl"] if openapi_url is None else openapi_url,
        "authenticationSecretNames": merge_secret_names(
            current["authenticationSecretNames"],
            add=secret,
            remove=remove_secret,
            clear=clear_secrets,
        ),
        "skillId": current["skill"]["id"] if current["skill"] else None,
    }
    if clear_skill:
        body["skillId"] = None
    elif skill:
        body["skillId"] = _call(settings, "GET", f"{skills_path(app_id)}/{skill}")["id"]

    updated = _call(settings, "PUT", _path(app_id), body)
    if not is_json_mode():
        print_success("Backend API updated.")
    render_config(updated)
