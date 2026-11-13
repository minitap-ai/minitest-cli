"""English action labels, kept identical to the webapp's run page.

Expected strings mirror webapp-minitest ``components/runs-page/gesture-glyph.test.ts``
and ``lib/utils/backend-call.test.ts``.
"""

import math

import pytest

from minitest_cli.commands.recording_action_format import truncate
from minitest_cli.commands.recording_action_labels import action_label


def label(**action: object) -> str:
    return action_label(dict(action))


class TestPointerLabels:
    def test_tap_names_target_label(self) -> None:
        assert label(type="tap", points=[[120, 640]], target={"label": "Sign in"}) == (
            "Tap on “Sign in”"
        )

    def test_tap_falls_back_to_identifier(self) -> None:
        target = {"label": " ", "identifier": "login_button"}
        assert label(type="tap", points=[[120, 640]], target=target) == "Tap on “login_button”"

    def test_tap_rounds_coordinates(self) -> None:
        assert label(type="tap", points=[[119.6, 640.4]]) == "Tap at (120, 640)"

    def test_tap_placeholder_point_keeps_plain_verb(self) -> None:
        assert label(type="tap", points=[[2, 3]]) == "Tap"
        assert label(type="tap", points=[[-4, 4]]) == "Tap"

    def test_tap_truncates_long_target(self) -> None:
        target = {"label": "Accept all cookies and continue browsing"}
        assert label(type="tap", target=target) == "Tap on “Accept all cookies and…”"

    def test_long_press_on_and_at(self) -> None:
        assert label(type="long_press", points=[[1080, 2200]]) == "Long press at (1080, 2200)"
        assert label(type="long_press", points=[[5, 5]], target={"label": "Row"}) == (
            "Long press on “Row”"
        )

    def test_click_on_and_at(self) -> None:
        assert label(type="click", points=[[300.2, 40.7]]) == "Click at (300, 41)"
        assert label(type="click", target={"label": "Save"}) == "Click on “Save”"
        assert label(type="click") == "Click"

    def test_tap_ignores_malformed_points(self) -> None:
        assert label(type="tap", points=[["a", 1], [math.nan, 2], [300, 400]]) == (
            "Tap at (300, 400)"
        )
        assert label(type="tap", points="nope", target="nope") == "Tap"


class TestTextLabels:
    def test_text_quotes_short_text(self) -> None:
        assert label(type="text", text="hello") == "Type “hello”"

    def test_text_truncates_and_collapses_whitespace(self) -> None:
        text = "line one\nline two " + "x" * 40
        assert label(type="text", text=text) == "Type “line one line two xxxxxxxxxxxxxxxxxxxxx…”"

    def test_text_names_field(self) -> None:
        assert label(type="text", text="a@b.co", target={"label": "Email"}) == (
            "Type into “Email”: “a@b.co”"
        )

    def test_text_empty_falls_back(self) -> None:
        assert label(type="text") == "Type text"
        assert label(type="text", text="  \n ") == "Type text"

    def test_truncate_keeps_short_values(self) -> None:
        assert truncate("short", 40) == "short"
        assert len(truncate("😀" * 50, 40)) == 40


class TestNetworkLabels:
    @pytest.mark.parametrize(
        ("condition", "expected"),
        [
            ("airplane_mode", "Airplane mode"),
            ("degraded", "Network degraded"),
            ("normal", "Network normal"),
            ("offline", "Network offline"),
            ("ultra_slow", "Network degraded"),
            ("slow", "Network degraded"),
            ("medium", "Network degraded"),
            ("full", "Network normal"),
        ],
    )
    def test_network_condition_including_legacy(self, condition: str, expected: str) -> None:
        assert label(type="network", networkCondition=condition) == expected

    @pytest.mark.parametrize(
        ("change", "expected"),
        [
            ("airplane_mode_on", "Airplane mode on"),
            ("airplane_mode_off", "Airplane mode off"),
            ("wifi_off", "Wi-Fi off"),
            ("wifi_on", "Wi-Fi on"),
            ("offline", "Network offline"),
            ("online", "Network online"),
        ],
    )
    def test_network_change_wins_over_condition(self, change: str, expected: str) -> None:
        action = {"type": "network", "networkCondition": "normal", "networkChange": change}
        assert action_label(action) == expected

    def test_network_unknown_and_missing(self) -> None:
        assert label(type="network", networkCondition="lte_lossy") == "Network · lte_lossy"
        assert label(type="network") == "Network"
        assert label(type="network", networkCondition=42) == "Network"


class TestOrientationAndLocationLabels:
    def test_orientation_labels(self) -> None:
        assert label(type="orientation", orientation="landscape") == "Rotate to landscape"
        assert label(type="orientation", orientation="portrait") == "Rotate to portrait"
        assert label(type="orientation") == "Rotate"

    def test_location_set_formats_coordinates(self) -> None:
        assert label(type="location", locationMode="set", latitude=48.8566, longitude=2.3522) == (
            "Setting location to 48.8566, 2.3522"
        )

    def test_location_set_negative_and_capped_decimals(self) -> None:
        action = {"latitude": -33.86881234567, "longitude": -151.2093}
        assert label(type="location", locationMode="set", **action) == (
            "Setting location to -33.868812, -151.2093"
        )
        assert label(type="location", latitude=0.0000001, longitude=10.0) == (
            "Setting location to 0, 10"
        )

    def test_location_set_without_coordinates_falls_back(self) -> None:
        assert label(type="location", locationMode="set") == "Location change"
        assert label(type="location", latitude=math.inf, longitude=1) == "Location change"

    def test_location_route_with_waypoints_and_speed(self) -> None:
        route = [[48.8566, 2.3522], [48.86, 2.34], [48.87, 2.33], [48.8738, 2.295]]
        assert label(type="location", locationMode="route", route=route, speedMps=13.89) == (
            "Moving from 48.8566, 2.3522 to 48.8738, 2.295 · 2 waypoints · 13.9 m/s"
        )

    def test_location_route_single_waypoint_no_speed(self) -> None:
        route = [[1, 2], [3, 4], [5, 6]]
        assert label(type="location", locationMode="route", route=route, speedMps=0) == (
            "Moving from 1, 2 to 5, 6 · 1 waypoint"
        )

    def test_location_route_too_short_and_clear(self) -> None:
        assert label(type="location", locationMode="route", route=[[1, 2]]) == (
            "Simulating a route"
        )
        assert label(type="location", locationMode="clear") == "Restoring real location"


class TestOtherLabels:
    def test_backend_shows_path_and_status(self) -> None:
        action = {"method": "POST", "statusCode": 201, "requestBody": '{"secret": 1}'}
        assert label(type="backend", url="https://api.x.io/api/v1/bets", **action) == (
            "POST /api/v1/bets · 201"
        )

    def test_backend_failed_without_status(self) -> None:
        assert label(type="backend", url="https://api.x.io", error="ECONNREFUSED") == (
            "GET / · failed"
        )
        assert label(type="backend", url="https://api.x.io/a") == "GET /a"
        assert label(type="backend") == "Backend call"

    def test_nav_and_key(self) -> None:
        assert label(type="nav", url="https://shop.io/cart") == "Navigate · https://shop.io/cart"
        assert label(type="nav") == "Navigate"
        assert label(type="key", description="Enter") == "Key · Enter"
        assert label(type="key") == "Key"

    def test_gestures_and_curves(self) -> None:
        assert label(type="scroll", deltaY=200) == "Scroll"
        assert label(type="swipe", points=[[1, 2], [100, 200]]) == "Swipe"
        assert label(type="drag", points=[[10, 20], [100, 200]]) == "Drag"
        assert label(type="pinch") == "Pinch"
        assert label(type="swipe", points=[[10, 10], [50, 60], [90, 10]]) == "Curved gesture"
        assert label(type="drag", points=[[10, 10], [50, 60], [90, 10]]) == "Curved gesture"

    def test_unknown_type_uses_type(self) -> None:
        assert label(type="teleport") == "teleport"
        assert label() == "unknown"
