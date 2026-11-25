"""`minitest persona default`: the persona a scenario created without `--persona` plays."""

from typing import Annotated, Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.persona_helpers import (
    current_app_id,
    handle_persona_response,
    personas_path,
    resolve_persona_id,
)
from minitest_cli.commands.test_account_helpers import (
    account_credentials_path,
    get_settings,
    is_json_mode,
    run_api_call,
)
from minitest_cli.utils.output import output, print_error, print_success


async def _set_default(app_id: str, ref: str) -> dict[str, Any]:
    async with ApiClient(get_settings()) as client:
        persona_id = await resolve_persona_id(client, app_id, ref)
        resp = await client.get(f"{personas_path(app_id)}/{persona_id}")
        handle_persona_response(resp)
        persona = resp.json()
        if not persona["accounts"]:
            print_error(
                f"Persona {persona['name']} has no test account yet. Add one with "
                f"`minitest test-account add --persona {persona_id} ...`."
            )
            raise typer.Exit(code=1)
        # The backend keeps the app's default on a test account; its persona is the default.
        account_id = persona["accounts"][0]["id"]
        resp = await client.put(f"{account_credentials_path(app_id, account_id)}/default")
        handle_persona_response(resp, resource="Test account")
        return {
            "personaId": persona_id,
            "personaName": persona["name"],
            "testAccountId": account_id,
        }


async def _clear_default(app_id: str) -> None:
    async with ApiClient(get_settings()) as client:
        resp = await client.delete(f"/api/v1/apps/{app_id}/test-profiles/default")
        handle_persona_response(resp, resource="App")


def register(app: typer.Typer) -> None:

    @app.command(name="default")
    def default_persona(
        persona: Annotated[str | None, typer.Argument(help="Persona ID or name.")] = None,
        clear: Annotated[
            bool, typer.Option("--clear", help="Remove the default: such scenarios play New user.")
        ] = False,
    ) -> None:
        """Set the persona a scenario plays when it is created without --persona."""
        if (persona is None) != clear:
            print_error("Give a persona, or --clear.")
            raise typer.Exit(code=1)
        app_id = current_app_id()
        if persona is None:
            run_api_call(_clear_default(app_id))
            if is_json_mode():
                output({"cleared": True}, json_mode=True)
            else:
                print_success(
                    "Default persona cleared: new scenarios without --persona play New user."
                )
            return
        data = run_api_call(_set_default(app_id, persona))
        if not is_json_mode():
            print_success(
                f"Default persona: {data['personaName']}. New scenarios without --persona play it."
            )
        output(data, json_mode=is_json_mode())
