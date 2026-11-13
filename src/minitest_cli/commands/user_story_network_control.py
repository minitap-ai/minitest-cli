"""Mark acceptance criteria that toggle or slow the device's network."""

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
from minitest_cli.utils.output import output, print_error, print_success


def _criterion_ids(story: dict[str, Any], selectors: list[str]) -> list[str]:
    criteria = story.get("acceptanceCriteria") or []
    ids: list[str] = []
    for selector in selectors:
        if not selector.isdigit():
            ids.append(selector)
            continue
        index = int(selector)
        if index < 1 or index > len(criteria):
            print_error(f"Criterion index {index} out of range (1-{len(criteria)}).")
            raise typer.Exit(code=1)
        ids.append(str(criteria[index - 1]["criterionId"]))
    return ids


def set_network_control(
    user_story_id: Annotated[str, typer.Argument(help="Scenario ID.")],
    criteria: Annotated[
        list[str],
        typer.Argument(
            help=(
                "Criteria to mark: 1-based index on a live scenario, or criterion ID "
                "(needed for a criterion created in a draft)."
            )
        ),
    ],
    off: Annotated[
        bool, typer.Option("--off", help="Clear the mark instead of setting it.")
    ] = False,
) -> None:
    """Mark criteria that toggle or slow the network (Wi-Fi off, airplane mode, slow network).

    On a device without network control (cloud iOS simulators) a marked criterion is skipped
    instead of judged; the scenario's other criteria still run.
    """
    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)
    app_id = resolve_app_id(settings, get_app_flag())

    async def _run() -> list[str]:
        async with ApiClient(settings) as client:
            story: dict[str, Any] = {}
            if any(selector.isdigit() for selector in criteria):
                resp = await client.get(f"{base_path(app_id)}/{user_story_id}")
                handle_response_error(resp)
                story = resp.json()
            ids = _criterion_ids(story, criteria)
            for criterion_id in ids:
                resp = await client.put(
                    f"/api/v1/apps/{app_id}/criteria/{criterion_id}/network-control",
                    json={"needsNetworkControl": not off},
                )
                handle_response_error(resp)
            return ids

    ids = run_api_call(_run())
    if json_mode:
        output({"criterionIds": ids, "needsNetworkControl": not off}, json_mode=True)
        return
    state = "cleared on" if off else "set on"
    print_success(f"Network-control mark {state} {len(ids)} criterion(s).")
