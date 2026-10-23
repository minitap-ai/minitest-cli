"""``secret lint``: check a text, file or scenario for secret references, gaps and leaks.

A leak is reported by position only: its text is never printed.
"""

from pathlib import Path
from typing import Annotated, Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.secret_helpers import JsonOption, command_context, request, secrets_path
from minitest_cli.commands.user_story_helpers import base_path, handle_response_error, run_api_call
from minitest_cli.utils.output import print_error, print_json, print_success, print_warning

Source = tuple[str, str]


async def lint_text(client: ApiClient, app_id: str, text: str) -> dict[str, Any]:
    path = f"{secrets_path(app_id)}/lint"
    return await request(client, "POST", path, json={"text": text}, collection=True) or {}


async def fetch_story(client: ApiClient, app_id: str, story_id: str) -> dict[str, Any]:
    resp = await client.get(f"{base_path(app_id)}/{story_id}")
    handle_response_error(resp)
    return resp.json()


def story_sources(story: dict[str, Any]) -> list[Source]:
    sources: list[Source] = [("description", story.get("description") or "")]
    for index, item in enumerate(story.get("acceptanceCriteria") or [], start=1):
        if isinstance(item, dict) and item.get("content"):
            sources.append((f"criterion {index}", item["content"]))
    return [(label, text) for label, text in sources if text]


def position(text: str, offset: int) -> str:
    before = text[: max(0, min(offset, len(text)))]
    return f"{before.count(chr(10)) + 1}:{len(before) - before.rfind(chr(10))}"


def has_problems(result: dict[str, Any]) -> bool:
    return bool(result.get("leaks") or result.get("missing"))


def render(label: str, text: str, result: dict[str, Any]) -> None:
    prefix = f"{label} " if label else ""
    for ref in result.get("references") or []:
        field = f".{ref['field']}" if ref.get("field") else ""
        at = position(text, int(ref.get("start", 0)))
        print(f"{prefix}{at} reference {{{{secret:{ref.get('name')}{field}}}}}")  # noqa: T201
    for name in result.get("missing") or []:
        print_error(
            f"{prefix}{name} is referenced but not set: minitest secret set {name} --kind <kind>"
        )
    for name in result.get("pending") or []:
        print_warning(
            f"{prefix}{name} has no value yet: runs that need it wait until a human sets it "
            f"(minitest secret set {name} --kind <kind>)"
        )
    for leak in result.get("leaks") or []:
        span = f"{position(text, int(leak['start']))}-{position(text, int(leak['end']))}"
        what = f"is the value of {leak['secret']}" if leak.get("secret") else "looks like a secret"
        hint = f"use {{{{secret:{leak['secret']}}}}}" if leak.get("secret") else "extract it"
        print_error(f"{prefix}{span} literal {what} — {hint}")
    for name in result.get("legacy") or []:
        print_warning(f"{prefix}${name} is legacy syntax, write {{{{secret:{name}}}}}")


def _read_sources(file: Path | None, text: str | None) -> list[Source]:
    if file is not None:
        return [(str(file), file.read_text(encoding="utf-8"))]
    return [("", text or "")]


def register(app: typer.Typer) -> None:

    @app.command(name="lint")
    def lint(
        file: Annotated[Path | None, typer.Option("--file", help="File to lint.")] = None,
        text: Annotated[str | None, typer.Option("--text", help="Text to lint.")] = None,
        scenario: Annotated[
            str | None, typer.Option("--scenario", help="Scenario ID to lint.")
        ] = None,
        json_flag: JsonOption = False,
    ) -> None:
        """References, missing/pending secrets, leaks, legacy $NAME (exit 1 on leak or missing)."""
        if sum(x is not None for x in (file, text, scenario)) != 1:
            print_error("Give exactly one of --file, --text or --scenario.")
            raise typer.Exit(code=1)
        settings, json_mode, app_id = command_context(json_flag)

        async def _run() -> list[tuple[str, str, dict[str, Any]]]:
            async with ApiClient(settings) as client:
                if scenario is not None:
                    sources = story_sources(await fetch_story(client, app_id, scenario))
                else:
                    sources = _read_sources(file, text)
                return [(lb, tx, await lint_text(client, app_id, tx)) for lb, tx in sources]

        results = run_api_call(_run())
        failed = any(has_problems(r) for _, _, r in results)
        if json_mode:
            print_json({"ok": not failed, "sources": [{"source": lb, **r} for lb, _, r in results]})
        else:
            for label, body, result in results:
                render(label, body, result)
            if not failed:
                print_success("No leaks or missing secrets.")
        if failed:
            raise typer.Exit(code=1)
