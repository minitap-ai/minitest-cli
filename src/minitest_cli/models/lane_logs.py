"""Log files of one scenario-run target, as served by testing-service."""

from typing import Literal

from minitest_cli.models.base import CamelModel


class LaneLogFile(CamelModel):
    kind: str
    file_name: str
    bytes: int | None = None
    compressed: bool
    url: str


class LaneCrash(CamelModel):
    kind: str
    title: str
    frame: str | None = None
    summary: str
    offset_ms: int


class LaneLogs(CamelModel):
    status: Literal["pending", "ready", "none"]
    unavailable_reason: str | None = None
    files: list[LaneLogFile]
    crashes: list[LaneCrash]
