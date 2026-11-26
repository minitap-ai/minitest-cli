"""Print a PR check's progress once per fact, whether it came from the stream or a poll.

Events and report snapshots are reduced to the same facts (state, plan, item,
question, verdict) keyed for de-duplication, so a reconnect that replays events or a
poll that re-reads the report never prints a line twice.
"""

import json
import os
import sys
import time
from collections.abc import Iterator
from typing import Any

from rich.markup import escape

from minitest_cli.commands.pr_follow import REPORT_EVENT, Event
from minitest_cli.commands.pr_render import console, item_line, plan_lines

TERMINAL_STATES = frozenset({"done", "errored", "cancelled"})
HEARTBEAT_SECONDS = 60.0
STATE_LINES = {
    "queued": "Queued",
    "preparing": "Preparing: Mini reads the PR, the suite and the open issues",
    "exploring": "Exploring and verifying on the device(s)",
    "errored": "[red]The check errored on our side[/red]",
}
GROUPS = {"preparing": "Prepare", "exploring": "Explore & verify"}


def in_github_actions() -> bool:
    return os.environ.get("GITHUB_ACTIONS") == "true"


def snapshot_events(report: dict[str, Any]) -> Iterator[Event]:
    push, state = report["push"], report["state"]
    checks = report.get("checks") or []
    if checks:
        yield Event("pr_check.plan", {"checks": checks, "push": push})
    if state not in TERMINAL_STATES:
        yield Event("pr_check.state", {"state": state, "push": push})
    for check in checks:
        for platform, result in (check.get("platforms") or {}).items():
            if result and result.get("verdict"):
                item = {"checkId": check["id"], "platform": platform, "tag": check.get("tag")}
                yield Event("pr_check.item", {**result, **item, "push": push})
    for question in report.get("questions") or []:
        if question.get("answer") is None:
            yield Event("pr_check.question", {**question, "push": push})
    if state in TERMINAL_STATES:
        if report.get("verdict"):
            verdict = {"verdict": report["verdict"], "counts": report.get("counts"), "push": push}
            yield Event("pr_check.verdict", verdict)
        yield Event("pr_check.state", {"state": state, "push": push})


def fact_key(event: Event) -> tuple[Any, ...]:
    data = event.data
    if event.type == "pr_check.item":
        return (event.type, data.get("checkId"), data.get("platform"), data.get("verdict"))
    if event.type == "pr_check.question":
        return (event.type, data.get("checkId"))
    if event.type in ("pr_check.state", "pr_check.suite"):
        return (event.type, data.get("state"))
    return (event.type,)


class Progress:
    def __init__(self, push: int, *, json_mode: bool) -> None:
        self.push = push
        self.json_mode = json_mode
        self.state = "queued"
        self.finished = False
        self.superseded_by: int | None = None
        # A stream replays the session from its start: an event without a push (an older
        # server's question) is only ours once the stream has reached our push.
        self._live = False
        self._seen: set[tuple[Any, ...]] = set()
        self._labels: dict[str, str] = {}
        self._results = 0
        self._group: str | None = None
        self._gha = in_github_actions() and not json_mode
        self._started = self._last_line = time.monotonic()

    def feed(self, event: Event) -> None:
        events = snapshot_events(event.data) if event.type == REPORT_EVENT else [event]
        for fact in events:
            if not self.finished:
                self._fact(fact)

    def _fact(self, event: Event) -> None:
        push = event.data.get("push")
        if push is None and not self._live:
            return
        if push is not None and push != self.push:
            if push > self.push:
                self.superseded_by, self.finished = push, True
            return
        if event.id is not None:
            self._live = True
        key = fact_key(event)
        if key in self._seen:
            return
        self._seen.add(key)
        if self.json_mode:
            line = {"type": event.type, "id": event.id, "data": event.data}
            print(json.dumps(line, default=str), flush=True)  # noqa: T201
        self._apply(event)

    def _apply(self, event: Event) -> None:
        data = event.data
        if event.type == "pr_check.state":
            self.state = data["state"]
            self._open_group(GROUPS.get(self.state))
            if self.state in STATE_LINES:
                self.line(STATE_LINES[self.state])
            self.finished = self.state in TERMINAL_STATES
        elif event.type == "pr_check.plan":
            self._labels = {c["id"]: c.get("label") or c["id"] for c in data["checks"]}
            for text in plan_lines(data["checks"]):
                self.line(text)
        elif event.type == "pr_check.item":
            self._results += 1
            self.line(item_line(data, self._labels.get(str(data.get("checkId")), "")))
        elif event.type == "pr_check.question":
            label = escape(self._labels.get(str(data.get("checkId")), "a check"))
            options = " / ".join(map(str, data.get("options") or []))
            ask = escape(str(data.get("ask")) + (f" ({options})" if options else ""))
            self.line(f"[yellow]? Question on {label}:[/yellow] {ask}")
        elif event.type == "pr_check.verdict":
            self._open_group(None)
            self.finished = True

    def _open_group(self, title: str | None) -> None:
        if not self._gha or title == self._group:
            return
        if self._group is not None:
            self.raw("::endgroup::")
        if title is not None:
            self.raw(f"::group::{title}")
        self._group = title

    def close(self) -> None:
        self._open_group(None)

    def raw(self, text: str) -> None:
        print(text, file=sys.stderr, flush=True)  # noqa: T201

    def line(self, markup: str) -> None:
        self._last_line = time.monotonic()
        if not self.json_mode:
            console.print(markup)

    def heartbeat_in(self) -> float:
        return max(0.0, self._last_line + HEARTBEAT_SECONDS - time.monotonic())

    def heartbeat(self) -> None:
        elapsed = int(time.monotonic() - self._started)
        self._last_line = time.monotonic()
        console.print(
            f"[dim]… still {self.state} ({elapsed // 60}m{elapsed % 60:02d}s,"
            f" {self._results} result(s) in)[/dim]"
        )
