"""`minitest brief` and `minitest app-guide`: the two versioned Knowledge v2 documents."""

from typing import Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.knowledge_helpers import (
    ContentFileOption,
    ContentOption,
    app_path,
    call_for_app,
    check_response,
    describe_actor,
    resolve_content,
)
from minitest_cli.commands.user_story_helpers import is_json_mode
from minitest_cli.utils.output import output, print_info, print_success


def _document_app(name: str, route: str, label: str, help_text: str) -> typer.Typer:
    group = typer.Typer(name=name, help=help_text, no_args_is_help=True)

    @group.command(name="get")
    def get_document() -> None:
        """Print the current content (with --json: content, version and author)."""

        async def _get(client: ApiClient, app_id: str) -> dict[str, Any]:
            resp = await client.get(app_path(app_id, route))
            check_response(resp, resource=label)
            return resp.json()

        record = call_for_app(_get)
        if is_json_mode():
            output(record, json_mode=True)
            return
        if not record.get("content"):
            print_info(f"No {label} written yet.")
            return
        print_info(_version_line(record))
        print(record["content"])  # noqa: T201

    @group.command(name="update")
    def update_document(
        content: ContentOption = None, content_file: ContentFileOption = None
    ) -> None:
        """Replace the content, creating a new version authored by you via the CLI."""
        body = {"content": resolve_content(content, content_file)}

        async def _put(client: ApiClient, app_id: str) -> dict[str, Any]:
            resp = await client.put(app_path(app_id, route), json=body)
            check_response(resp, resource=label)
            return resp.json()

        record = call_for_app(_put)
        if is_json_mode():
            output(record, json_mode=True)
            return
        print_success(f"{label} updated (version {record.get('versionNumber')}).")
        print(record.get("versionNumber"))  # noqa: T201

    return group


def _version_line(record: dict[str, Any]) -> str:
    author = describe_actor(record.get("actor"))
    line = f"Version {record.get('versionNumber')}"
    if author:
        line += f" by {author}"
    if record.get("createdAt"):
        line += f", {record['createdAt']}"
    return line


brief_app = _document_app(
    "brief",
    "product-brief",
    "Product brief",
    "Product brief: what the app is, who uses it and its core flows (max 2000 chars).",
)
app_guide_app = _document_app(
    "app-guide",
    "app-guide",
    "App guide",
    "App guide: how to use the app when testing it (navigation, quirks, test data).",
)
