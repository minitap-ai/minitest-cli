"""Playbook retrieval for `minitest init`."""

import asyncio

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.init_playbook import FALLBACK_PLAYBOOK
from minitest_cli.core.config import Settings

PLAYBOOK_PATH = "/api/v1/onboarding/cli/playbook"

SOURCE_SERVER = "server"
SOURCE_EMBEDDED = "embedded"


async def _fetch_playbook(settings: Settings) -> str | None:
    async with ApiClient(settings) as client:
        resp = await client.get(PLAYBOOK_PATH)
    if resp.status_code >= 400 or not resp.text.strip():
        return None
    return resp.text


def load_playbook(settings: Settings) -> tuple[str, str]:
    """Return the served playbook and its source, falling back to the embedded copy.

    `init` is the one command that runs before the agent has authenticated, so any
    failure here must degrade to the embedded copy instead of exiting.
    """
    try:
        served = asyncio.run(_fetch_playbook(settings))
    except Exception:  # noqa: BLE001
        served = None
    if served is None:
        return FALLBACK_PLAYBOOK, SOURCE_EMBEDDED
    return served, SOURCE_SERVER
