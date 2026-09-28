"""Customer-allowed setup commits: let validation activate a story's commit step."""

from typing import Annotated, Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.user_story_helpers import (
    base_path,
    get_app_flag,
    get_settings,
    handle_response_error,
    is_json_mode,
    run_api_call,
)
from minitest_cli.core.app_context import resolve_app_id
from minitest_cli.core.auth import require_auth
from minitest_cli.utils.output import output, print_error, print_info, print_success

CUSTOMER_QUOTE_MAX_LENGTH = 1000


def _permission_path(app_id: str, user_story_id: str) -> str:
    return f"{base_path(app_id)}/{user_story_id}/setup-commit-permission"


def allow_setup_commit(
    user_story_id: Annotated[str, typer.Argument(help="User-story ID.")],
    customer_quote: Annotated[
        str,
        typer.Option(
            "--customer-quote",
            help=(
                "The customer's own words allowing validation to activate this story's "
                f"commit step, quoted verbatim (max {CUSTOMER_QUOTE_MAX_LENGTH} chars)."
            ),
        ),
    ],
) -> None:
    """Allow validation to perform this story's commit so dependent stories can start from it."""
    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)
    quote = customer_quote.strip()
    if not quote or len(quote) > CUSTOMER_QUOTE_MAX_LENGTH:
        print_error(f"--customer-quote must be 1-{CUSTOMER_QUOTE_MAX_LENGTH} characters.")
        raise typer.Exit(code=1)
    app_id = resolve_app_id(settings, get_app_flag())

    async def _run() -> dict[str, Any]:
        async with ApiClient(settings) as client:
            resp = await client.put(
                _permission_path(app_id, user_story_id), json={"customerQuote": quote}
            )
            handle_response_error(resp)
            return resp.json()

    data = run_api_call(_run())
    if json_mode:
        output(data, json_mode=True)
        return
    print_success(f"Setup commit allowed for user story {user_story_id}")
    print_info(f"Customer quote: {data.get('customerQuote', quote)}")


def revoke_setup_commit(
    user_story_id: Annotated[str, typer.Argument(help="User-story ID.")],
) -> None:
    """Stop validation from performing this story's commit."""
    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)
    app_id = resolve_app_id(settings, get_app_flag())

    async def _run() -> None:
        async with ApiClient(settings) as client:
            resp = await client.delete(_permission_path(app_id, user_story_id))
            handle_response_error(resp)

    run_api_call(_run())
    if json_mode:
        output({"revoked": True, "id": user_story_id}, json_mode=True)
    else:
        print_success(f"Setup commit revoked for user story {user_story_id}")
