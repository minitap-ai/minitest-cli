"""Reference documents of the agent skill: served by Minitest, bundled as the fallback.

The topic names come from the server (or from the bundled ``index.json``), never from
this code, so a topic added on the server reaches every CLI version.
"""

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx

from minitest_cli.api.client import CHANNEL_HEADER, CLI_HEADER, CLI_HEADER_VALUE
from minitest_cli.api.errors import format_network_error
from minitest_cli.core.config import Settings
from minitest_cli.utils import skill_bundle

REFERENCE_PATH = "/api/skills/reference"
INDEX_FILE = "index.json"

_TIMEOUT = httpx.Timeout(10.0, connect=3.0)


class UnknownTopicError(Exception):
    def __init__(self, topic: str, topics: list[str]) -> None:
        super().__init__(f"Unknown reference topic: {topic}")
        self.topic = topic
        self.topics = topics


class ReferenceUnavailableError(Exception):
    """Minitest did not serve the reference: unreachable, or a server without the route."""


async def _get(settings: Settings, path: str) -> httpx.Response:
    headers = {CHANNEL_HEADER: settings.channel, CLI_HEADER: CLI_HEADER_VALUE}
    async with httpx.AsyncClient(
        base_url=settings.api_url, headers=headers, timeout=_TIMEOUT, follow_redirects=True
    ) as client:
        return await client.get(path)


def _request(settings: Settings, path: str) -> httpx.Response:
    try:
        return asyncio.run(_get(settings, path))
    except httpx.HTTPError as exc:
        raise ReferenceUnavailableError(format_network_error(exc)) from exc


def _unknown_topics(response: httpx.Response) -> list[str] | None:
    try:
        topics = response.json().get("details", {}).get("topics")
    except (ValueError, AttributeError):
        return None
    return topics if isinstance(topics, list) else None


def fetch_index(settings: Settings) -> list[dict[str, Any]]:
    response = _request(settings, REFERENCE_PATH)
    if response.status_code != 200:
        raise ReferenceUnavailableError(f"HTTP {response.status_code}")
    try:
        index = response.json()
    except ValueError as exc:
        raise ReferenceUnavailableError("the server did not answer JSON") from exc
    if not isinstance(index, list):
        raise ReferenceUnavailableError("the server answered with an unexpected index")
    return index


def fetch_topic(settings: Settings, topic: str) -> str:
    response = _request(settings, f"{REFERENCE_PATH}/{topic}")
    if response.status_code == 200:
        return response.text
    # A server without the route also answers 404, but without the list of topics.
    topics = _unknown_topics(response) if response.status_code == 404 else None
    if topics is not None:
        raise UnknownTopicError(topic, topics)
    raise ReferenceUnavailableError(f"HTTP {response.status_code}")


def _reference_dir() -> Path:
    return skill_bundle.bundle_dir() / "reference"


def bundled_index() -> list[dict[str, Any]]:
    return json.loads((_reference_dir() / INDEX_FILE).read_text(encoding="utf-8"))


def bundled_topic(topic: str) -> str:
    topics = [entry["topic"] for entry in bundled_index()]
    if topic not in topics:
        raise UnknownTopicError(topic, topics)
    return (_reference_dir() / f"{topic}.md").read_text(encoding="utf-8")
