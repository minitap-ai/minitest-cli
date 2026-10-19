"""`minitest draft get --watch`: poll a draft until it reaches a stable state.

Two stopping rules, so an agent can wait for exactly what it acts on next:

- ``idle``: Mini is not writing and has no turn queued — read the reply, answer an
  ask, or send the next message. The default.
- ``settled``: idle, no check running and no build Conductor started for the draft
  in flight — the verdict is in.

A closed draft (merged/discarded) and a draft waiting on a person stop both.
"""

import asyncio
import time
from enum import StrEnum
from typing import Any

import httpx

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.draft_helpers import DraftTarget, raise_for_status
from minitest_cli.commands.draft_render import mini_status
from minitest_cli.utils.output import print_info

CLOSED_STATES = frozenset({"merged", "discarded"})
TURN_REASON_CODES = frozenset({"authoring", "queued"})
BUILD_IN_FLIGHT = frozenset({"requested", "building"})


def _now() -> float:
    return time.monotonic()


class WatchUntil(StrEnum):
    IDLE = "idle"
    SETTLED = "settled"


def is_stable(draft: dict[str, Any], until: WatchUntil) -> bool:
    state = draft.get("state")
    if state in CLOSED_STATES or draft.get("needsUser"):
        return True
    idle = not draft.get("miniWriting") and draft.get("stateReasonCode") not in TURN_REASON_CODES
    if until is WatchUntil.IDLE:
        return idle
    # The counts move before the state does: a check just started still reads "drafting".
    checking = (draft.get("counts") or {}).get("validating", 0) > 0
    return idle and state != "validating" and not checking and not building(draft)


def building(draft: dict[str, Any]) -> bool:
    """Conductor is building the commit the draft waits for (e.g. a linked PR's head)."""
    build = (draft.get("waitingFor") or {}).get("build") or {}
    return build.get("status") in BUILD_IN_FLIGHT


def _progress(draft: dict[str, Any]) -> str:
    reason = draft.get("stateReason") or "-"
    return f"{draft.get('state')} · Mini {mini_status(draft)} · {reason}"


async def watch(
    target: DraftTarget, path: str, *, until: WatchUntil, interval: float, timeout: float
) -> tuple[dict[str, Any], bool]:
    """Return the last snapshot and whether it is stable (False means the watch timed out)."""
    deadline = _now() + timeout
    last_line = ""
    async with ApiClient(target.settings, base_url=target.settings.conductor_url) as client:
        while True:
            try:
                resp = await client.get(path, params=target.params)
            except httpx.TransportError:
                if _now() >= deadline:
                    raise
                await asyncio.sleep(interval)
                continue
            if resp.status_code >= 500 and _now() < deadline:
                await asyncio.sleep(interval)
                continue
            raise_for_status(resp, resource="Draft")
            draft: dict[str, Any] = resp.json()
            line = _progress(draft)
            if line != last_line:
                print_info(line)
                last_line = line
            if is_stable(draft, until):
                return draft, True
            if _now() >= deadline:
                return draft, False
            await asyncio.sleep(interval)
