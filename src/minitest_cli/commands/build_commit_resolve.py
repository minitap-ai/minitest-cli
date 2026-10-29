"""Bridge the two build id spaces `minitest build from-commit` straddles.

``from-commit`` triggers the build through apps-manager and gets an apps-manager
build id back. Every id-consuming command downstream — ``minitest build list``,
``minitest run start --ios-build/--android-build`` — speaks *testing-service*
ids instead. The apps-manager trigger response carries no testing-service id, so
the CLI has to look it up.

The lookup uses only documented public fields of the build list response:
testing-service rows expose ``commitSha`` and ``platform``, and a row exists as
soon as the build is triggered (it starts out ``pending``), so the newest row
matching the triggered ``(commitSha, platform)`` pair is the counterpart. No
storage-path parsing, no polling.
"""

from collections.abc import Iterable

import httpx

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.build_helpers import BuildStatusFilter, base_path
from minitest_cli.core.config import Settings
from minitest_cli.models import BuildListResponse, BuildResponse
from minitest_cli.models.commit_build import TriggeredBuild

RESOLVE_TIMEOUT_SECONDS = 20.0
RESOLVE_PAGE_SIZE = 100
# ``build list`` filters to completed builds server-side when no status is given,
# and a freshly triggered build is ``pending`` — so ask for every status.
ALL_BUILD_STATUSES = [status.value for status in BuildStatusFilter]

RUN_START_FLAGS = {"ios": "--ios-build", "android": "--android-build"}


async def fetch_candidate_builds(settings: Settings, app_id: str) -> list[BuildResponse]:
    """Fetch the most recent testing-service build rows for the app."""
    params: dict[str, object] = {
        "page": 1,
        "page_size": RESOLVE_PAGE_SIZE,
        "status": ALL_BUILD_STATUSES,
    }
    async with ApiClient(settings) as client:
        resp = await client.get(
            f"{base_path(app_id)}/builds", params=params, timeout=RESOLVE_TIMEOUT_SECONDS
        )
    resp.raise_for_status()
    return BuildListResponse.model_validate(resp.json()).items


def select_build_id(
    rows: Iterable[BuildResponse], *, commit_sha: str | None, platform: str | None
) -> str | None:
    """Return the newest row id for an exact ``(commitSha, platform)`` match."""
    if not commit_sha or not platform:
        return None
    matches = [row for row in rows if row.commit_sha == commit_sha and row.platform == platform]
    if not matches:
        return None
    return max(matches, key=lambda row: row.created_at).id


async def resolve_testing_service_ids(
    settings: Settings, app_id: str, builds: list[TriggeredBuild]
) -> dict[str, str | None]:
    """Map every triggered apps-manager build id to its testing-service id.

    Best effort by design: the build has already been queued by the time we get
    here, so a lookup that errors, times out, or matches nothing must never turn
    a successful trigger into a failed command. Unresolved ids come back as
    ``None`` and the caller reports the trigger anyway.
    """
    unresolved: dict[str, str | None] = {build.id: None for build in builds}
    if not builds:
        return unresolved
    try:
        rows = await fetch_candidate_builds(settings, app_id)
    except (httpx.HTTPError, ValueError):
        return unresolved
    return {
        build.id: select_build_id(rows, commit_sha=build.commit_sha, platform=build.platform)
        for build in builds
    }
