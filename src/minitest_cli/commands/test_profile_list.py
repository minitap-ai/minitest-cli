"""Test-profile listing commands (split out of test_profile.py to satisfy 200-LOC cap)."""

from typing import Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.test_profile_helpers import (
    PROFILE_TABLE_HEADERS,
    SHARED_PATH,
    app_base_path,
    format_profile_row,
    get_app_flag,
    get_settings,
    handle_profile_response,
    is_json_mode,
    run_api_call,
)
from minitest_cli.core.app_context import resolve_app_id
from minitest_cli.core.auth import require_auth
from minitest_cli.utils.output import output, print_info, print_table


def register(app: typer.Typer) -> None:
    """Register the list/list-shared commands onto the given Typer sub-app."""

    @app.command(name="list")
    def list_profiles() -> None:
        """List test profiles for the active app."""
        settings = get_settings()
        json_mode = is_json_mode()
        require_auth(settings)
        app_id = resolve_app_id(settings, get_app_flag())

        async def _run() -> Any:
            async with ApiClient(settings) as client:
                resp = await client.get(app_base_path(app_id))
                handle_profile_response(resp)
                return resp.json()

        data = run_api_call(_run())
        items = data["items"] if isinstance(data, dict) and "items" in data else data
        if json_mode:
            output(items, json_mode=True)
            return
        if not items:
            print_info("No test profiles found.")
            return
        rows = [format_profile_row(p) for p in items]
        print_table(PROFILE_TABLE_HEADERS, rows, title=f"Test profiles ({len(items)})")

    @app.command(name="list-shared")
    def list_shared() -> None:
        """List globally-shared test profiles (tenant-agnostic)."""
        settings = get_settings()
        json_mode = is_json_mode()
        require_auth(settings)

        async def _run() -> Any:
            async with ApiClient(settings) as client:
                resp = await client.get(SHARED_PATH)
                handle_profile_response(resp)
                return resp.json()

        data = run_api_call(_run())
        items = data["items"] if isinstance(data, dict) and "items" in data else data
        if json_mode:
            output(items, json_mode=True)
            return
        if not items:
            print_info("No shared test profiles found.")
            return
        rows = [format_profile_row(p) for p in items]
        print_table(PROFILE_TABLE_HEADERS, rows, title=f"Shared test profiles ({len(items)})")
