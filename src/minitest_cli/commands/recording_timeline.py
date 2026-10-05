"""Place a run's criterion verdicts and agent actions on its reduced recording.

Mirrors webapp-minitest ``lib/utils/video-time-mapping.ts`` so the seconds the
CLI reports land on the same frames the run page seeks to.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from minitest_cli.models.recording import (
    RecordingTimeline,
    SegmentMap,
    TimelineAction,
    TimelineCriterion,
)
from minitest_cli.models.story_run import CriterionResult, PlatformRun, StoryRunResponse

SEGMENT_MAP_TOLERANCE = 0.15


@dataclass(frozen=True)
class RecordingSource:
    url: str
    segment_map: SegmentMap | None
    started_at: datetime | None
    action_trace: dict | None


def map_to_compressed_time(real_sec: float, segment_map: SegmentMap | None) -> float:
    if not segment_map:
        return real_sec
    for seg in segment_map:
        if real_sec <= seg.original_end:
            return seg.compressed_start + max(0.0, real_sec - seg.original_start) / seg.speed
    return segment_map[-1].compressed_end


def is_segment_map_applied(segment_map: SegmentMap | None, duration_sec: float | None) -> bool:
    """False when the served file is the uncut recording despite carrying a segment map."""
    if not segment_map or not duration_sec:
        return True
    expected = segment_map[-1].compressed_end
    return not expected or abs(duration_sec - expected) / expected <= SEGMENT_MAP_TOLERANCE


def recording_source(platform_run: PlatformRun, device_index: int) -> RecordingSource | None:
    rec = next((r for r in platform_run.device_recordings if r.device_index == device_index), None)
    if device_index != 1:
        if rec is None:
            return None
        return RecordingSource(
            rec.url, rec.segment_map, rec.recording_started_at, rec.agent_action_trace
        )
    # The primary device's entry carries no segment map or trace: those stay on the platform.
    url = platform_run.recording_url or (rec.url if rec else None)
    if url is None:
        return None
    return RecordingSource(
        url,
        platform_run.segment_map or (rec.segment_map if rec else None),
        platform_run.recording_started_at or (rec.recording_started_at if rec else None),
        platform_run.agent_action_trace or (rec.agent_action_trace if rec else None),
    )


def _results_for(
    run: StoryRunResponse, platform_run: PlatformRun, device_index: int
) -> list[CriterionResult]:
    def same_target(r: CriterionResult) -> bool:
        if r.srp_id and platform_run.srp_id:
            return r.srp_id == platform_run.srp_id
        return r.platform == platform_run.platform

    return [r for r in run.results if same_target(r) and device_index in r.device_indexes]


def _criterion(
    result: CriterionResult, started_at: datetime | None, segment_map: SegmentMap | None
) -> TimelineCriterion:
    window: tuple[float, float] | None = None
    if started_at and result.observed_from and result.observed_until:
        raw_from = (result.observed_from - started_at).total_seconds()
        raw_until = (result.observed_until - started_at).total_seconds()
        if raw_until > 0:
            window = (
                map_to_compressed_time(max(0.0, raw_from), segment_map),
                map_to_compressed_time(raw_until, segment_map),
            )
    return TimelineCriterion(
        result_id=result.id,
        criterion_id=result.criterion_id,
        content=result.content,
        status=result.status,
        criticality=result.criticality,
        fail_reason=result.fail_reason,
        result_summary=result.result_summary,
        observed_from_sec=round(window[0], 3) if window else None,
        observed_until_sec=round(window[1], 3) if window else None,
    )


def _actions(trace: dict | None, segment_map: SegmentMap | None) -> list[TimelineAction]:
    if not trace:
        return []
    raw_actions: list[dict[str, Any]] = trace.get("actions") or []
    intent_by_index = {
        idx: intent.get("description")
        for intent in trace.get("intents") or []
        for idx in intent.get("actionIndices") or []
    }

    def seconds(offset_ms: float | None) -> float | None:
        if offset_ms is None:
            return None
        return round(map_to_compressed_time(offset_ms / 1000, segment_map), 3)

    actions = [
        TimelineAction(
            at_sec=seconds(action.get("offsetMs", 0)) or 0.0,
            end_sec=seconds(action.get("endOffsetMs")),
            type=action.get("type", "unknown"),
            target=(action.get("target") or {}).get("label"),
            url=action.get("url"),
            intent=intent_by_index.get(idx),
        )
        for idx, action in enumerate(raw_actions)
    ]
    return sorted(actions, key=lambda a: a.at_sec)


def build_timeline(
    run: StoryRunResponse,
    platform_run: PlatformRun,
    *,
    device_index: int,
    source: RecordingSource,
    video_path: str,
    duration_sec: float | None,
) -> RecordingTimeline:
    applied = is_segment_map_applied(source.segment_map, duration_sec)
    segment_map = source.segment_map if applied else None
    results = sorted(
        _results_for(run, platform_run, device_index),
        key=lambda r: r.observed_from or r.created_at,
    )
    return RecordingTimeline(
        story_run_id=run.id,
        user_story_name=run.user_story_name,
        platform=platform_run.platform,
        srp_id=platform_run.srp_id,
        device_index=device_index,
        video_path=video_path,
        duration_sec=duration_sec,
        time_base="compressed" if segment_map else "raw",
        recording_started_at=source.started_at,
        criteria=[_criterion(r, source.started_at, segment_map) for r in results],
        actions=_actions(source.action_trace, segment_map),
    )
