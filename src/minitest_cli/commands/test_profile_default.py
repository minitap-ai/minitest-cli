"""Commands for managing the default test profile."""

from typing import Annotated, Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.test_profile_helpers import (
    app_base_path,
    get_app_flag,
    get_settings,
    handle_profile_response,
    is_json_mode,
    run_api_call,
)
from minitest_cli.core.app_context import resolve_app_id
from minitest_cli.core.auth import require_auth
from minitest_cli.utils.output import output, print_success


def register(app: typer.Typer) -> None:

    @app.command(name="set-default")
    def set_default(
        profile_id: Annotated[str, typer.Argument(help="Test profile ID to set as default.")],
    ) -> None:
        """Set a test profile as the default for the app.

        New user stories without an explicit ``--profile`` will auto-assign
        this profile.
        """
        settings = get_settings()
        json_mode = is_json_mode()
        require_auth(settings)
        app_id = resolve_app_id(settings, get_app_flag())

        async def _run() -> dict[str, Any]:
            async with ApiClient(settings) as client:
                resp = await client.put(
                    f"{app_base_path(app_id)}/{profile_id}/default",
                )
                handle_profile_response(resp)
                return resp.json()

        data = run_api_call(_run())
        if not json_mode:
            print_success(f"Default profile set: {data.get('name', profile_id)}")
        output(data, json_mode=json_mode)

    @app.command(name="clear-default")
    def clear_default() -> None:
        """Remove the default profile for the app."""
        settings = get_settings()
        json_mode = is_json_mode()
        require_auth(settings)
        app_id = resolve_app_id(settings, get_app_flag())

        async def _run() -> None:
            async with ApiClient(settings) as client:
                resp = await client.delete(f"{app_base_path(app_id)}/default")
                handle_profile_response(resp)

        run_api_call(_run())
        if json_mode:
            output({"cleared": True}, json_mode=True)
        else:
            print_success("Default profile cleared.")
