"""Models for a run recording and the timeline that places a run's events on it."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from minitest_cli.models.base import CamelModel


class Segment(BaseModel):
    """One span of the reduced recording; the server serialises these in snake_case."""

    original_start: float
    original_end: float
    compressed_start: float
    compressed_end: float
    speed: float


SegmentMap = list[Segment]


class DeviceRecording(CamelModel):
    device_index: int
    url: str
    segment_map: SegmentMap | None = None
    agent_action_trace: dict | None = None
    recording_started_at: datetime | None = None


class TimelineCriterion(CamelModel):
    result_id: str
    criterion_id: str | None = None
    content: str | None = None
    status: str | None = None
    criticality: str | None = None
    fail_reason: str | None = None
    result_summary: str | None = None
    observed_from_sec: float | None = None
    observed_until_sec: float | None = None
    frames_path: str | None = None


class TimelineAction(CamelModel):
    at_sec: float
    end_sec: float | None = None
    type: str
    target: str | None = None
    url: str | None = None
    intent: str | None = None


class RecordingTimeline(CamelModel):
    """Every second here is a position in ``video_path``, ready to seek or extract frames at.

    ``time_base`` is ``compressed`` when static stretches of the video were
    sped up (the usual case) and ``raw`` when the file is the uncut recording.
    """

    story_run_id: str
    user_story_name: str | None = None
    platform: str
    srp_id: str | None = None
    device_index: int
    video_path: str
    duration_sec: float | None = None
    time_base: Literal["compressed", "raw"]
    recording_started_at: datetime | None = None
    criteria: list[TimelineCriterion] = []
    actions: list[TimelineAction] = []
