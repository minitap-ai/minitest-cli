"""User-story ``suggest-deps`` command.

Split out of ``user_story.py`` to fit the 200-line file cap. Wired in
``user_story.py`` via ``app.command(name="suggest-deps")(...)`` like
``user_story_modify`` does for update/delete. Helper logic
(GET-all-stories, PATCH-grouped-per-child, JSON-mode emit) lives in
``user_story_suggest_helpers``.
"""

import sys
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
from minitest_cli.commands.user_story_suggest_helpers import (
    apply_suggestions,
    emit_json,
    fetch_all_stories_inner,
)
from minitest_cli.core.app_context import resolve_app_id
from minitest_cli.core.auth import require_auth
from minitest_cli.models.user_story import SuggestDependenciesResponse
from minitest_cli.utils.output import output, print_error, print_info, print_success, print_table


def suggest_dependencies(
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            "-y",
            help="Apply every suggestion without prompting. Required in non-TTY contexts.",
        ),
    ] = False,
) -> None:
    """Ask the agent to propose user-story dependencies for this app.

    Fallback for the "I genuinely don't know what the deps should be"
    case. **Prefer ``--depends-on`` directly on ``create`` / ``update``**
    when you can reason about the dep yourself — it's cheaper,
    deterministic, and avoids the LLM round-trip.
    """
    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)
    app_id = resolve_app_id(settings, get_app_flag())

    async def _suggest() -> SuggestDependenciesResponse:
        async with ApiClient(settings) as client:
            resp = await client.post(f"{base_path(app_id)}/suggest-dependencies")
            handle_response_error(resp)
            return SuggestDependenciesResponse.model_validate(resp.json())

    response = run_api_call(_suggest())

    if not response.suggestions:
        if json_mode:
            output({"suggestions": [], "applied": []}, json_mode=True)
        else:
            print_info(
                "No dependencies suggested. If you already know which flows "
                "gate which, declare them with `user-story update --depends-on`."
            )
        return

    if json_mode:
        # JSON mode renders ids only — no need to fetch the full story
        # set just to look up display names. ``emit_json`` does its own
        # PATCH round-trip when ``--yes`` is set.
        emit_json(response, settings, app_id, yes=yes)
        return

    # Pull every story so the prompt table can render names beside ids.
    async def _stories() -> dict[str, dict[str, Any]]:
        async with ApiClient(settings) as client:
            return await fetch_all_stories_inner(client, app_id)

    stories_by_id = run_api_call(_stories())

    def _label(sid: str) -> str:
        name = stories_by_id.get(sid, {}).get("name") or "<unknown>"
        return f"{name} ({sid[:8]})"

    rows = [
        [
            _label(s.user_story_id),
            _label(s.depends_on_user_story_id),
            f"{s.confidence:.2f}",
            s.reasoning,
        ]
        for s in response.suggestions
    ]
    print_table(
        ["Story", "Depends on", "Confidence", "Reasoning"],
        rows,
        title=f"Suggested dependencies ({len(response.suggestions)})",
    )

    # Non-TTY without --yes would hang ``typer.confirm``; fail fast instead.
    if not yes and not sys.stdin.isatty():
        print_error(
            "suggest-deps in a non-TTY context requires --yes (or pipe `yes` "
            "in). Skipping to avoid hanging on confirmation prompts."
        )
        raise typer.Exit(code=1)

    accepted = (
        list(response.suggestions)
        if yes
        else [
            s
            for s in response.suggestions
            if typer.confirm(
                f"Apply: {_label(s.user_story_id)} → {_label(s.depends_on_user_story_id)}?"
            )
        ]
    )
    if not accepted:
        print_info("No suggestions applied.")
        return

    applied = apply_suggestions(settings, app_id, accepted)
    print_success(
        f"Applied {sum(len(p) for p in applied.values())} dependency edge(s) "
        f"across {len(applied)} user stor{'y' if len(applied) == 1 else 'ies'}."
    )
