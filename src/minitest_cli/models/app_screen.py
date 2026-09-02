"""Pydantic models for the screen map (``GET /api/v1/apps/{app_id}/screens``).

Casing seam — the one thing to get right here. testing-service serialises the
*envelope* in camelCase (``ScreenMapResponse`` / ``ScreenNodeResponse`` extend
``BaseApiModel``, which carries an alias generator), but it embeds ``outgoing``
and ``context`` as the DB models verbatim, and those extend ``DbModelConfig``,
which has **no** alias generator. So a node arrives as::

    {"screenKey": "welcome", ..., "outgoing": [{"to_screen_key": ...}]}

camelCase outside, snake_case inside. The models below mirror that exactly:
``ScreenEdge`` / ``ScreenContext`` / ``ScreenPrecondition`` are plain
``BaseModel``s, deliberately *not* ``CamelModel``.

The failure mode is on the **write** side, not the read side. ``CamelModel``
sets ``populate_by_name``, so it would still happily *parse* snake_case input —
which is exactly what makes the mistake easy to ship. What breaks is
``--json``: ``model_dump(by_alias=True)`` would emit ``toScreenKey`` where the
API emits ``to_screen_key``, so anything piping the CLI's JSON would silently
read a different shape than the same field served by the API.
``TestWireShape`` in ``tests/test_screens_commands.py`` pins the emitted keys.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from minitest_cli.models.base import CamelModel


class ScreenPrecondition(BaseModel):
    """One machine-testable precondition. Snake_case on the wire."""

    kind: str
    ref: str | None = None


class ScreenEdge(BaseModel):
    """An observed onward affordance from a screen. Snake_case on the wire.

    A ``parked`` edge is the crawl saying "I saw the way on and chose not to
    follow it" — collectively, the parked edges are the unexplored frontier.
    """

    action: str
    to_screen_key: str | None = None
    onward_observed: bool = False
    parked: bool = False
    parked_reason: str | None = None
    parked_kind: str | None = None
    last_verified_at: datetime | None = None
    consecutive_failures: int = 0


class ScreenContext(BaseModel):
    """What it takes to stand on a screen. Snake_case on the wire."""

    requires_auth: bool = False
    persona_ref: str | None = None
    preconditions: list[ScreenPrecondition] = Field(default_factory=list)
    reachable_via: str | None = None
    deeplink_uri: str | None = None
    cheaply_reachable: bool = True
    cheaply_reachable_reason: str | None = None


class ScreenNode(CamelModel):
    """One node of the screen map. camelCase envelope."""

    id: str
    platform: str
    screen_key: str
    display_name: str
    depth: int
    area: str | None = None
    discovered_at: datetime
    first_reached_at: datetime
    blocked_reason: str | None = None
    gated_by: str | None = None
    screenshot_path: str | None = None
    screenshot_url: str | None = None
    outgoing: list[ScreenEdge] = Field(default_factory=list)
    context: ScreenContext | None = None


class ScreenMapResponse(CamelModel):
    """The whole map for an app, in one fetch. camelCase envelope."""

    app_id: str
    platform: str | None = None
    screen_count: int
    screens: list[ScreenNode] = Field(default_factory=list)
