"""Conductor access for `minitest run ask`: the questions Mini asks while a run executes.

Conductor calls them escalations. One is open on the customer's side when it is
``awaiting_answer`` and ``answerable`` (the caller may answer it); the others are
either still being triaged by Minitap or already closed.
"""

from typing import Any

import httpx

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.draft_helpers import raise_for_status, run_conductor
from minitest_cli.commands.run_helpers import ensure_uuid
from minitest_cli.core.config import Settings
from minitest_cli.utils.output import print_warning

ESCALATIONS_PATH = "/api/v1/escalations"
WAITING_STATE = "awaiting_answer"
RESOURCE = "Question"
CONFLICT_HINT = "Re-read it with `minitest run ask get <ask-id>` before deciding what to do next."


def is_waiting(escalation: dict[str, Any]) -> bool:
    """Whether this question is waiting on the caller's answer."""
    return escalation.get("state") == WAITING_STATE and bool(escalation.get("answerable"))


def has_pending_proposal(escalation: dict[str, Any]) -> bool:
    return escalation.get("proposal") is not None and escalation.get("proposalStatus") in (
        "pending",
        None,
    )


async def _request(settings: Settings, method: str, path: str, **kwargs: Any) -> httpx.Response:
    async with ApiClient(settings, base_url=settings.conductor_url) as client:
        return await client.request(method, path, **kwargs)


async def fetch_batch_escalations(settings: Settings, batch_id: str) -> list[dict[str, Any]]:
    """Every customer-readable question on a batch; raises httpx errors to the caller."""
    resp = await _request(settings, "GET", ESCALATIONS_PATH, params={"batchId": batch_id})
    resp.raise_for_status()
    return resp.json().get("escalations") or []


async def count_waiting(settings: Settings, batch_id: str) -> int | None:
    """How many questions wait on the caller, or None when Conductor cannot say."""
    try:
        escalations = await fetch_batch_escalations(settings, batch_id)
    except (httpx.HTTPError, ValueError):
        return None
    return sum(is_waiting(e) for e in escalations)


def warn_waiting(batch_id: str, count: int | None) -> None:
    """Point at `run ask list` when questions wait on the caller."""
    if count:
        noun = "question" if count == 1 else "questions"
        print_warning(
            f"Mini has {count} {noun} waiting for you on this run: "
            f"`minitest run ask list {batch_id}`."
        )


def call(settings: Settings, method: str, path: str, **kwargs: Any) -> Any:
    """One Conductor request, exiting with the right code on any error."""
    resp = run_conductor(_request(settings, method, path, **kwargs))
    raise_for_status(resp, resource=RESOURCE, conflict_hint=CONFLICT_HINT)
    return resp.json() if resp.content else None


def list_escalations(settings: Settings, batch_id: str) -> list[dict[str, Any]]:
    ensure_uuid(batch_id, kind="batch id")
    body = call(settings, "GET", ESCALATIONS_PATH, params={"batchId": batch_id})
    return (body or {}).get("escalations") or []


def ask_path(ask_id: str, suffix: str = "") -> str:
    ensure_uuid(ask_id, kind="ask id")
    return f"{ESCALATIONS_PATH}/{ask_id}{suffix}"


def get_escalation(settings: Settings, ask_id: str) -> dict[str, Any]:
    return call(settings, "GET", ask_path(ask_id))
