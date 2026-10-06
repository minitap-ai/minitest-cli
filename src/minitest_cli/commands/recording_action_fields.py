"""The detail of one raw trace action that a recording timeline keeps.

Request and response bodies of backend calls are deliberately left out: the
timeline is a lightweight index of what happened, not a payload dump.
"""

from typing import Any

from minitest_cli.commands.recording_action_labels import action_label
from minitest_cli.commands.recording_action_parse import (
    POINTER_TYPES,
    as_int,
    as_number,
    as_str,
    network_condition,
    pointer_point,
    route_of,
    target_of,
)

ORIENTATIONS = frozenset({"landscape", "portrait"})
LOCATION_MODES = frozenset({"set", "route", "clear"})


def _one_of(value: Any, allowed: frozenset[str]) -> str | None:
    return value if isinstance(value, str) and value in allowed else None


def _pointer_fields(action: dict[str, Any]) -> dict[str, Any]:
    point = pointer_point(action) if action.get("type") in POINTER_TYPES else None
    return {"x": point[0], "y": point[1]} if point else {}


def _route(action: dict[str, Any]) -> list[list[float]] | None:
    route = route_of(action)
    return [[lat, lng] for lat, lng in route] if route else None


def action_fields(action: dict[str, Any]) -> dict[str, Any]:
    """``TimelineAction`` keyword arguments beyond timing, type, target, url and intent."""
    is_key = action.get("type") == "key"
    # Gestures carry their own `method` (tap_ref, label, coordinates); only a
    # backend call's method is an HTTP verb, so only those expose it.
    is_backend = action.get("type") == "backend"
    text = as_str(action.get("text"))
    return {
        "label": action_label(action),
        **_pointer_fields(action),
        "identifier": as_str(target_of(action).get("identifier")),
        "text": text or None,
        "network_condition": network_condition(action),
        "network_change": as_str(action.get("networkChange")),
        "orientation": _one_of(action.get("orientation"), ORIENTATIONS),
        "location_mode": _one_of(action.get("locationMode"), LOCATION_MODES),
        "latitude": as_number(action.get("latitude")),
        "longitude": as_number(action.get("longitude")),
        "route": _route(action),
        "speed_mps": as_number(action.get("speedMps")),
        "method": as_str(action.get("method")) if is_backend else None,
        "status_code": as_int(action.get("statusCode")) if is_backend else None,
        "error": as_str(action.get("error")) if is_backend else None,
        "duration_ms": as_number(action.get("durationMs")),
        "key": (as_str(action.get("description")) or None) if is_key else None,
    }
