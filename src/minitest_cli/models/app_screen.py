"""Pydantic models for the screen tree (``GET /api/v1/apps/{app_id}/screen-tree``).

Casing seam: the envelope is camelCase, but each screen's ``context`` is the
testing-service DB model embedded verbatim, which is snake_case. ``ScreenContext``
and ``ScreenPrecondition`` are therefore plain ``BaseModel``s, not ``CamelModel``:
``--json`` must emit ``requires_auth`` exactly as the API serves it.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from minitest_cli.models.base import CamelModel

AUTO_ELEMENT_KEY = "(auto)"
AUTO_ELEMENT_KIND = "auto"


class ScreenPrecondition(BaseModel):
    kind: str
    ref: str | None = None


class ScreenContext(BaseModel):
    requires_auth: bool = False
    persona_ref: str | None = None
    preconditions: list[ScreenPrecondition] = Field(default_factory=list)
    reachable_via: str | None = None
    deeplink_uri: str | None = None
    cheaply_reachable: bool = True
    cheaply_reachable_reason: str | None = None


class TransitionCounts(CamelModel):
    explored: int = 0
    pending: int = 0
    blocked: int = 0
    skipped: int = 0


class TreeCounts(TransitionCounts):
    screens: int = 0


class ScreenTransition(CamelModel):
    """``(from screen, element) → to screen``, tagged with the account that walked it.

    ``persona_ref`` is ``""`` for signed-out, never null.
    """

    id: str
    from_screen_key: str
    element_key: str
    element_label: str
    element_kind: str
    to_screen_key: str | None = None
    status: str
    reason: str | None = None
    persona_ref: str = ""
    gated_by: str | None = None
    first_walked_at: datetime | None = None
    last_walked_at: datetime | None = None
    is_tree_edge: bool = False

    @property
    def is_auto(self) -> bool:
        return self.element_kind == AUTO_ELEMENT_KIND or self.element_key == AUTO_ELEMENT_KEY


class TreeScreen(CamelModel):
    """A screen placed in the tree. ``depth`` is null for detached screens."""

    screen_key: str
    display_name: str
    area: str | None = None
    notes: str | None = None
    context: ScreenContext | None = None
    screenshot_path: str | None = None
    screenshot_url: str | None = None
    first_reached_at: datetime | None = None
    depth: int | None = None
    parent_transition_id: str | None = None
    child_transition_ids: list[str] = Field(default_factory=list)
    outgoing_transition_ids: list[str] = Field(default_factory=list)
    incoming_transition_ids: list[str] = Field(default_factory=list)
    counts: TransitionCounts = Field(default_factory=TransitionCounts)


class ScreenTree(CamelModel):
    """One platform's tree: screens, every transition between them, and the detached rest."""

    platform: str
    root_screen_key: str | None = None
    counts: TreeCounts = Field(default_factory=TreeCounts)
    screens: list[TreeScreen] = Field(default_factory=list)
    transitions: list[ScreenTransition] = Field(default_factory=list)
    detached_screen_keys: list[str] = Field(default_factory=list)


class ScreenTreeResponse(CamelModel):
    app_id: str
    trees: list[ScreenTree] = Field(default_factory=list)
