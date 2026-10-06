"""Pydantic models for tenant scenario tags, mirroring testing-service schemas."""

from enum import StrEnum

from minitest_cli.models.base import CamelModel


class TagColor(StrEnum):
    VIOLET = "violet"
    BLUE = "blue"
    EMERALD = "emerald"
    AMBER = "amber"
    CYAN = "cyan"
    SLATE = "slate"
    INDIGO = "indigo"
    ORANGE = "orange"
    PINK = "pink"
    GRAY = "gray"
    RED = "red"
    TEAL = "teal"


class TagRef(CamelModel):
    id: str
    name: str
    color: str


class TagResponse(TagRef):
    description: str | None = None
    scenario_count: int = 0
