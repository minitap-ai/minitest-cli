from typing import Annotated, Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.test_file_helpers import (
    FILE_TABLE_HEADERS,
    base_path,
    format_file_row,
    get_app_flag,
    get_settings,
    handle_file_response,
    is_json_mode,
    run_api_call,
)
from minitest_cli.core.app_context import resolve_app_id
from minitest_cli.core.auth import require_auth
from minitest_cli.utils.output import output, print_info, print_table


def register(app: typer.Typer) -> None:

    @app.command(name="list")
    def list_files(
        kind: Annotated[
            str | None,
            typer.Option("--kind", help="Filter by kind (image|document|video|audio|other)."),
        ] = None,
        page: Annotated[int, typer.Option("--page", min=1, help="Page number.")] = 1,
        page_size: Annotated[
            int, typer.Option("--page-size", min=1, max=100, help="Items per page.")
        ] = 20,
    ) -> None:
        settings = get_settings()
        json_mode = is_json_mode()
        require_auth(settings)
        app_id = resolve_app_id(settings, get_app_flag())

        params: dict[str, Any] = {"page": page, "page_size": page_size}
        if kind is not None:
            params["kind"] = kind

        async def _run() -> Any:
            async with ApiClient(settings) as client:
                resp = await client.get(base_path(app_id), params=params)
                handle_file_response(resp)
                return resp.json()

        data = run_api_call(_run())
        items = data["items"] if isinstance(data, dict) and "items" in data else data
        if json_mode:
            output(items, json_mode=True)
            return
        if not items:
            print_info("No test files found.")
            return
        rows = [format_file_row(f) for f in items]
        print_table(FILE_TABLE_HEADERS, rows, title=f"Test files ({len(items)})")
