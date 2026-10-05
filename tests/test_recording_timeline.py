"""Placing criterion verdicts and agent actions on a run's reduced recording.

The fixture mirrors a real story-run detail payload: two targets, a primary
device recording whose entry carries no segment map, and a recording sped up
36x over a static stretch.
"""

from datetime import datetime, timedelta

from minitest_cli.commands.recording_timeline import build_timeline, recording_source
from minitest_cli.models.story_run import StoryRunResponse

STARTED = "2026-10-03T19:43:30Z"


def _seg(orig: tuple[float, float], comp: tuple[float, float], speed: int) -> dict:
    return {
        "original_start": orig[0],
        "original_end": orig[1],
        "compressed_start": comp[0],
        "compressed_end": comp[1],
        "speed": speed,
    }


SEGMENT_MAP = [_seg((0, 10), (0, 10), 1), _seg((10, 46), (10, 11), 36), _seg((46, 56), (11, 21), 1)]


def _at(seconds_after_start: int) -> str:
    return (datetime.fromisoformat(STARTED) + timedelta(seconds=seconds_after_start)).isoformat()


def _result(rid: str, srp: str, status: str, window: tuple[int, int]) -> dict:
    return {
        "id": rid,
        "storyRunId": "run-1",
        "srpId": srp,
        "criterionVersionId": f"cv-{rid}",
        "platform": "android" if srp == "srp-android" else "ios",
        "status": status,
        "success": status == "success",
        "observedFrom": _at(window[0]),
        "observedUntil": _at(window[1]),
        "createdAt": _at(window[1]),
    }


def _run() -> StoryRunResponse:
    return StoryRunResponse.model_validate(
        {
            "id": "run-1",
            "userStoryId": "us-1",
            "createdAt": STARTED,
            "platforms": [
                {
                    "platform": "android",
                    "srpId": "srp-android",
                    "recordingUrl": "https://storage/signed.mp4",
                    "recordingStartedAt": STARTED,
                    "segmentMap": SEGMENT_MAP,
                    "deviceRecordings": [
                        {"deviceIndex": 1, "url": "https://storage/signed.mp4", "segmentMap": None}
                    ],
                    "agentActionTrace": {
                        "actions": [
                            {"type": "swipe", "offsetMs": 50000},
                            {
                                "type": "tap",
                                "offsetMs": 5000,
                                "endOffsetMs": 6000,
                                "target": {"label": "Continue"},
                            },
                        ],
                        "intents": [{"description": "Advance onboarding", "actionIndices": [1]}],
                    },
                },
                {"platform": "ios", "srpId": "srp-ios"},
            ],
            "results": [
                _result("late", "srp-android", "failed", (48, 50)),
                _result("early", "srp-android", "success", (5, 7)),
                _result("other-target", "srp-ios", "success", (5, 7)),
                _result("before-recording", "srp-android", "skipped", (-30, -20)),
            ],
        }
    )


def _timeline(duration_sec: float | None):
    run = _run()
    platform_run = run.platforms[0]
    source = recording_source(platform_run, 1)
    assert source is not None
    return build_timeline(
        run,
        platform_run,
        device_index=1,
        source=source,
        video_path="recording.mp4",
        duration_sec=duration_sec,
    )


class TestRecordingTimeline:
    def test_build_timeline_places_criteria_on_compressed_video(self) -> None:
        timeline = _timeline(duration_sec=21.0)

        assert timeline.time_base == "compressed"
        windows = {
            c.result_id: (c.observed_from_sec, c.observed_until_sec) for c in timeline.criteria
        }
        # 48s into the raw recording sits 2s into the last real-speed segment.
        assert windows == {
            "before-recording": (None, None),
            "early": (5.0, 7.0),
            "late": (13.0, 15.0),
        }

    def test_build_timeline_binds_intents_and_orders_actions(self) -> None:
        timeline = _timeline(duration_sec=21.0)

        assert [(a.type, a.at_sec, a.end_sec, a.target, a.intent) for a in timeline.actions] == [
            ("tap", 5.0, 6.0, "Continue", "Advance onboarding"),
            ("swipe", 15.0, None, None, None),
        ]

    def test_build_timeline_keeps_raw_seconds_when_file_is_uncut(self) -> None:
        timeline = _timeline(duration_sec=56.0)

        assert timeline.time_base == "raw"
        late = next(c for c in timeline.criteria if c.result_id == "late")
        assert (late.observed_from_sec, late.observed_until_sec) == (48.0, 50.0)
