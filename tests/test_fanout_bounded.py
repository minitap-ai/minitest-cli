"""The `run verdicts` and issues-hint fan-outs: same output, at most 6 requests in flight."""

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

import httpx
import pytest

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.issues_helpers import fetch_other_batch_hint
from minitest_cli.commands.verdicts_helpers import fetch_verdicts
from minitest_cli.commands.verdicts_projection import project_story, project_target
from minitest_cli.core.config import Settings
from minitest_cli.models.batch import BatchResponse
from minitest_cli.models.story_run import BatchVerdictsResponse, StoryRunResponse

APP_ID = "app-1"
BATCH_ID = "batch-1"
RUNS = 25
NOW = "2026-11-03T12:00:00Z"
APP_PATH = f"/api/v1/apps/{APP_ID}"
Handler = Callable[[httpx.Request], Coroutine[Any, Any, httpx.Response]]


def _detail(index: int) -> dict:
    status = "failed" if index % 3 == 0 else "success"
    platform = "ios" if index % 2 else "android"
    return {
        "id": f"run-{index}",
        "userStoryId": f"us-{index}",
        "createdAt": NOW,
        "platforms": [{"platform": platform, "executionState": "completed"}],
        "results": [
            {
                "id": f"res-{index}",
                "storyRunId": f"run-{index}",
                "criterionVersionId": f"cv-{index}",
                "platform": platform,
                "status": status,
                "success": status == "success",
                "evidence": f"evidence {index}",
                "createdAt": NOW,
            }
        ],
    }


BATCH = {
    "id": BATCH_ID,
    "appId": APP_ID,
    "tenantId": "tenant-1",
    "source": "cli",
    "status": "completed",
    "createdAt": NOW,
    "targets": [{"id": "bt-ios", "platform": "ios", "label": "iOS"}],
    "storyRuns": [
        {
            "id": f"run-{i}",
            "userStoryId": f"us-{i}",
            "userStoryName": f"Story {i}",
            "createdAt": NOW,
        }
        for i in range(RUNS)
    ],
}


class _Probe:
    def __init__(self) -> None:
        self.in_flight = 0
        self.peak = 0

    def wrap(self, reply: Callable[[httpx.Request], httpx.Response], delay) -> Handler:
        async def handle(request: httpx.Request) -> httpx.Response:
            self.in_flight += 1
            self.peak = max(self.peak, self.in_flight)
            try:
                await asyncio.sleep(delay(request))
                return reply(request)
            finally:
                self.in_flight -= 1

        return handle


@pytest.fixture
def wire(monkeypatch):
    def install(handler: Handler) -> Settings:
        async_client = httpx.AsyncClient
        monkeypatch.setattr(
            "minitest_cli.api.client.httpx.AsyncClient",
            lambda **kwargs: async_client(transport=httpx.MockTransport(handler), **kwargs),
        )
        return Settings(token="test-token", api_url="https://api.test")

    return install


def _verdicts_reply(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == f"{APP_PATH}/batches/{BATCH_ID}":
        return httpx.Response(200, json=BATCH)
    return httpx.Response(200, json=_detail(int(path.rsplit("-", 1)[1])))


def _late_first(request: httpx.Request) -> float:
    """Earlier runs answer later, so completion order is scrambled."""
    tail = request.url.path.rsplit("run-", 1)
    return 0.0 if len(tail) == 1 else 0.001 * (RUNS - int(tail[1]))


def _expected(**flags: bool) -> BatchVerdictsResponse:
    """What the command printed before the fan-out was bounded: one story per run, batch order."""
    batch = BatchResponse.model_validate(BATCH)
    stories = [
        project_story(
            StoryRunResponse.model_validate(_detail(i)),
            platform=None,
            user_story_name=f"Story {i}",
            **flags,
        )
        for i in range(RUNS)
    ]
    return BatchVerdictsResponse(
        batch_id=BATCH_ID,
        app_id=APP_ID,
        targets=[project_target(t) for t in batch.targets],
        stories=[s for s in stories if s is not None],
    )


class TestVerdictsFanout:
    @pytest.mark.parametrize("only_failed", [False, True])
    @pytest.mark.parametrize("verbose", [False, True])
    def test_fetch_verdicts_output_unchanged_with_bounded_fanout(
        self, wire, only_failed: bool, verbose: bool
    ) -> None:
        probe = _Probe()
        settings = wire(probe.wrap(_verdicts_reply, _late_first))

        result = asyncio.run(
            fetch_verdicts(
                settings, APP_ID, BATCH_ID, platform=None, only_failed=only_failed, verbose=verbose
            )
        )

        expected = _expected(only_failed=only_failed, verbose=verbose)
        assert result.model_dump(mode="json") == expected.model_dump(mode="json")
        assert probe.peak == 6


class TestIssuesHintFanout:
    def test_other_batch_hint_counts_with_bounded_fanout(self, wire) -> None:
        batch_ids = [f"b-{i}" for i in range(30)]

        def reply(request: httpx.Request) -> httpx.Response:
            if request.url.path == f"{APP_PATH}/batches":
                items = [
                    {
                        "id": b,
                        "appId": APP_ID,
                        "tenantId": "t",
                        "source": "cli",
                        "status": "completed",
                        "createdAt": NOW,
                    }
                    for b in batch_ids
                ]
                return httpx.Response(200, json={"items": items, "total": len(items)})
            index = int(request.url.params["batch_id"].split("-")[1])
            return httpx.Response(200, json={"count": index % 4})

        probe = _Probe()
        settings = wire(probe.wrap(reply, lambda _r: 0.001))

        async def run() -> tuple[int, int]:
            async with ApiClient(settings) as client:
                return await fetch_other_batch_hint(client, APP_ID, "b-0")

        others = [i % 4 for i in range(1, 30)]
        assert asyncio.run(run()) == (sum(c > 0 for c in others), sum(others))
        assert probe.peak == 6
