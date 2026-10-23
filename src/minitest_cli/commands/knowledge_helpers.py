"""Shared plumbing for the Knowledge v2 commands: brief, app-guide, glossary, knowledge."""

from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Annotated, Any

import httpx
import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands._response_errors import format_validation_field_errors
from minitest_cli.commands.user_story_helpers import (
    extract_detail,
    get_app_flag,
    get_settings,
    handle_response_error,
    run_api_call,
)
from minitest_cli.core.app_context import resolve_app_id
from minitest_cli.core.auth import require_auth
from minitest_cli.utils.output import print_error

KNOWLEDGE_V2_DISABLED = "knowledge_v2_disabled"

ContentOption = Annotated[str | None, typer.Option("--content", help="New content (inline).")]
ContentFileOption = Annotated[
    Path | None,
    typer.Option(
        "--content-file",
        help="Path to a file whose contents become the new content.",
        exists=True,
        readable=True,
        dir_okay=False,
    ),
]


def app_path(app_id: str, suffix: str) -> str:
    return f"/api/v1/apps/{app_id}/{suffix}"


def check_response(resp: httpx.Response, *, resource: str) -> None:
    if resp.status_code < 400:
        return
    body = _json_body(resp)
    if resp.status_code == 409 and body.get("error") == KNOWLEDGE_V2_DISABLED:
        print_error(
            "Knowledge v2 (Product brief, App guide, Glossary) is not enabled for this "
            "workspace. Use `minitest app-knowledge` instead, or ask Minitap to enable it."
        )
        raise typer.Exit(code=1)
    if resp.status_code == 409:
        print_error(extract_detail(resp) or f"{resource} conflicts with an existing one.")
        raise typer.Exit(code=1)
    field_errors = format_validation_field_errors(body) if resp.status_code == 422 else None
    if field_errors:
        print_error(f"Invalid {resource}: {field_errors}")
        raise typer.Exit(code=1)
    handle_response_error(resp, resource=resource)


def _json_body(resp: httpx.Response) -> dict[str, Any]:
    try:
        body = resp.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def call_for_app[T](action: Callable[[ApiClient, str], Coroutine[Any, Any, T]]) -> T:
    settings = get_settings()
    require_auth(settings)
    app_id = resolve_app_id(settings, get_app_flag())

    async def _run() -> T:
        async with ApiClient(settings) as client:
            return await action(client, app_id)

    return run_api_call(_run())


def resolve_content(content: str | None, content_file: Path | None) -> str:
    if (content is None) == (content_file is None):
        print_error("Provide exactly one of --content or --content-file.")
        raise typer.Exit(code=1)
    text = content_file.read_text(encoding="utf-8") if content_file else content or ""
    if not text.strip():
        print_error("Content must not be empty.")
        raise typer.Exit(code=1)
    return text


def describe_actor(actor: Any) -> str:
    if not isinstance(actor, dict):
        return ""
    kind, channel = actor.get("kind") or "", actor.get("channel") or ""
    return f"{kind} ({channel})" if kind and channel else kind or channel
