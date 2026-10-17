"""The action detail a recording's timeline.json keeps, as it is written to disk."""

import math

from minitest_cli.commands.recording_timeline import _actions


def dumped(*actions: dict) -> list[dict]:
    timeline_actions = _actions({"actions": list(actions)}, None)
    return [a.model_dump(mode="json", by_alias=True, exclude_none=True) for a in timeline_actions]


class TestPointerFields:
    def test_tap_keeps_coordinates_identifier_and_target(self) -> None:
        target = {"role": "button", "label": "Sign in", "identifier": "login", "bounds": [0, 0]}
        [action] = dumped(
            {"type": "tap", "offsetMs": 1000, "points": [[119.6, 640.4]], "target": target}
        )
        assert action == {
            "atSec": 1.0,
            "type": "tap",
            "target": "Sign in",
            "label": "Tap on “Sign in”",
            "x": 120,
            "y": 640,
            "identifier": "login",
        }

    def test_tap_placeholder_point_omits_coordinates(self) -> None:
        [action] = dumped({"type": "click", "offsetMs": 0, "points": [[3, -2]]})
        assert action == {"atSec": 0.0, "type": "click", "label": "Click"}

    def test_swipe_never_gets_tap_coordinates(self) -> None:
        [action] = dumped({"type": "swipe", "offsetMs": 0, "points": [[100, 200], [300, 400]]})
        assert "x" not in action and action["label"] == "Swipe"


class TestDetailFields:
    def test_text_keeps_full_text(self) -> None:
        text = "a" * 60
        [action] = dumped({"type": "text", "offsetMs": 0, "text": text, "target": {"label": "Bio"}})
        assert action["text"] == text
        assert action["label"] == f"Type into “Bio”: “{'a' * 39}…”"

    def test_network_fields_are_camel_case_and_normalized(self) -> None:
        raw = {
            "type": "network",
            "offsetMs": 0,
            "networkCondition": "slow",
            "networkChange": "wifi_off",
        }
        [action] = dumped(raw)
        assert action["networkCondition"] == "degraded"
        assert action["networkChange"] == "wifi_off"
        assert action["label"] == "Wi-Fi off"

    def test_location_route_fields(self) -> None:
        route = [[48.85, 2.35], ["bad"], [48.87, 2.29]]
        raw = {
            "type": "location",
            "offsetMs": 0,
            "locationMode": "route",
            "route": route,
            "speedMps": 1.5,
        }
        [action] = dumped(raw)
        assert action["locationMode"] == "route"
        assert action["route"] == [[48.85, 2.35], [48.87, 2.29]]
        assert action["speedMps"] == 1.5
        assert action["label"] == "Moving from 48.85, 2.35 to 48.87, 2.29 · 1.5 m/s"

    def test_backend_never_copies_bodies(self) -> None:
        raw = {
            "type": "backend",
            "offsetMs": 0,
            "method": "POST",
            "url": "https://api.x.io/v1/bets?debug=1",
            "statusCode": 500,
            "durationMs": 42,
            "requestBody": '{"password": "hunter2"}',
            "responseBody": "boom",
        }
        [action] = dumped(raw)
        assert action["statusCode"] == 500 and action["durationMs"] == 42
        assert action["method"] == "POST"
        assert "requestBody" not in action and "responseBody" not in action
        assert "hunter2" not in str(action) and "boom" not in str(action)

    def test_key_and_orientation(self) -> None:
        key, rotate = dumped(
            {"type": "key", "offsetMs": 0, "description": "Enter"},
            {"type": "orientation", "offsetMs": 1, "orientation": "landscape"},
        )
        assert key["key"] == "Enter" and key["label"] == "Key · Enter"
        assert rotate["orientation"] == "landscape"

    def test_wrong_types_and_non_finite_numbers_are_dropped(self) -> None:
        raw = {
            "type": "location",
            "offsetMs": 0,
            "latitude": math.nan,
            "longitude": "2.3",
            "speedMps": math.inf,
            "orientation": "upside_down",
            "statusCode": True,
            "target": "not-a-dict",
        }
        [action] = dumped(raw)
        assert action == {"atSec": 0.0, "type": "location", "label": "Location change"}


class TestIntentAndGestureMethod:
    def test_gesture_method_is_not_reported_as_http_method(self) -> None:
        [action] = dumped(
            {"type": "tap", "offsetMs": 0, "points": [[360, 516]], "method": "tap_ref"}
        )
        assert "method" not in action and "statusCode" not in action
        assert action["label"] == "Tap at (360, 516)"

    def test_device_action_description_is_its_intent(self) -> None:
        [action] = dumped(
            {
                "type": "network",
                "offsetMs": 0,
                "networkChange": "airplane_mode_on",
                "description": "Enable airplane mode and check banner",
            }
        )
        assert action["intent"] == "Enable airplane mode and check banner"

    def test_intent_from_intents_wins_over_description(self) -> None:
        trace = {
            "actions": [{"type": "text", "offsetMs": 0, "text": "hi", "description": "own"}],
            "intents": [{"description": "Sign in", "actionIndices": [0]}],
        }
        [action] = _actions(trace, None)
        assert action.intent == "Sign in"

    def test_web_key_name_is_not_an_intent(self) -> None:
        [action] = dumped({"type": "key", "offsetMs": 0, "description": "Enter"})
        assert "intent" not in action and action["key"] == "Enter"
