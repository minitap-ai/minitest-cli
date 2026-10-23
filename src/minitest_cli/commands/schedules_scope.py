"""The "What runs" flags of `minitest schedules`: suite, tags minus exclusions, or picked."""

from dataclasses import dataclass
from typing import Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.run_helpers import is_uuid
from minitest_cli.commands.schedules_spec import fail
from minitest_cli.commands.tags_helpers import resolve_tag_ids
from minitest_cli.commands.user_story_helpers import EXIT_NOT_FOUND, fetch_all_user_stories
from minitest_cli.utils.output import print_error


@dataclass
class ScopeFlags:
    suite: bool
    tags: list[str] | None
    excludes: list[str] | None
    scenarios: list[str] | None

    @property
    def given(self) -> bool:
        return bool(self.suite or self.tags or self.scenarios)

    def check(self) -> None:
        if sum(bool(mode) for mode in (self.suite, self.tags, self.scenarios)) > 1:
            fail("Pick one of --suite, --tag or --scenario.")
        if self.excludes and not self.tags:
            fail("--exclude only applies with --tag.")


async def _scenario_ids(client: ApiClient, app_id: str, refs: list[str]) -> list[str]:
    if all(is_uuid(ref) for ref in refs):
        return refs
    by_name = {
        str(s.get("name", "")).casefold(): str(s["id"])
        for s in await fetch_all_user_stories(client, app_id, {})
    }
    ids = []
    for ref in refs:
        found = ref if is_uuid(ref) else by_name.get(ref.strip().casefold())
        if found is None:
            print_error(f"Scenario not found: {ref!r}. Use a scenario name or UUID.")
            raise typer.Exit(code=EXIT_NOT_FOUND)
        ids.append(found)
    return ids


async def resolve_scope(client: ApiClient, app_id: str, flags: ScopeFlags) -> dict[str, Any]:
    if flags.tags:
        return {
            "mode": "tags",
            "tagIds": await resolve_tag_ids(client, app_id, flags.tags),
            "excludedIds": await _scenario_ids(client, app_id, flags.excludes or []),
        }
    if flags.scenarios:
        return {"mode": "pick", "scenarioIds": await _scenario_ids(client, app_id, flags.scenarios)}
    return {"mode": "suite"}
