"""Follow a PR check: its event stream, resumed with Last-Event-ID, polled when it drops.

Every time the stream ends or fails, the report is read once and queued as a
``pr_check.report`` snapshot, then the stream is retried ``POLL_SECONDS`` later. So
progress and the end of the check still arrive while the stream is unavailable.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.draft_helpers import DraftTarget
from minitest_cli.commands.pr_api import check_path, raise_for_status

POLL_SECONDS = 15.0
# The server sends a heartbeat comment at least every 15 s; silence past this is a dead stream.
STREAM_TIMEOUT = httpx.Timeout(30.0, read=45.0)
REPORT_EVENT = "pr_check.report"


@dataclass
class Event:
    type: str
    data: dict[str, Any]
    id: str | None = None


@dataclass
class _Frame:
    id: str | None = None
    type: str = "message"
    data: list[str] = field(default_factory=list)


async def parse_sse(lines: AsyncIterator[str]) -> AsyncIterator[Event]:
    frame = _Frame()
    async for line in lines:
        if not line:
            if frame.data:
                yield Event(frame.type, json.loads("\n".join(frame.data)), frame.id)
            frame = _Frame()
            continue
        if line.startswith(":"):
            continue
        name, _, value = line.partition(":")
        value = value.removeprefix(" ")
        if name == "id":
            frame.id = value
        elif name == "event":
            frame.type = value
        elif name == "data":
            frame.data.append(value)


class Follower:
    def __init__(self, client: ApiClient, target: DraftTarget, check_id: str, push: int):
        self._client = client
        self._target = target
        self._check_id = check_id
        self._push = push
        self.last_event_id: str | None = None

    async def run(self, queue: asyncio.Queue[Event]) -> None:
        while True:
            try:
                await self._stream(queue)
            except httpx.TransportError:
                pass
            report = await self.report()
            if report is not None:
                await queue.put(Event(REPORT_EVENT, report))
            await asyncio.sleep(POLL_SECONDS)

    async def _stream(self, queue: asyncio.Queue[Event]) -> None:
        headers = {"Accept": "text/event-stream"}
        if self.last_event_id:
            headers["Last-Event-ID"] = self.last_event_id
        path = check_path(self._check_id, "/events")
        async with self._client.stream(
            "GET", path, params=self._target.params, headers=headers, timeout=STREAM_TIMEOUT
        ) as resp:
            if resp.status_code in (401, 403):
                await resp.aread()
                raise_for_status(resp, what="Following the PR check")
            if resp.status_code >= 400:
                return
            async for event in parse_sse(resp.aiter_lines()):
                if event.id:
                    self.last_event_id = event.id
                await queue.put(event)

    async def report(self) -> dict[str, Any] | None:
        """The push's report, or None while the server cannot be reached."""
        params = {**self._target.params, "push": self._push}
        try:
            resp = await self._client.get(check_path(self._check_id), params=params)
        except httpx.TransportError:
            return None
        if resp.status_code >= 500:
            return None
        raise_for_status(resp, what="Reading the PR check")
        return resp.json()
