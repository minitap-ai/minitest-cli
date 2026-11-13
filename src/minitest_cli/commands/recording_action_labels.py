"""The one-line English label the webapp shows for an agent action.

Mirrors webapp-minitest ``gestureLabel`` (``components/runs-page/gesture-glyph.tsx``,
``lib/utils/agent-action-labels.ts``, ``lib/utils/backend-call.ts``) and its
English copy, so the CLI's timeline reads the same as the run page.
"""

import re
from collections.abc import Callable
from typing import Any

from minitest_cli.commands.recording_action_format import (
    FALLBACKS,
    NETWORK_CHANGES,
    NETWORK_CONDITION_LABELS,
    ORIENTATIONS,
    POINTER_VERBS,
    TARGET_LIMIT,
    TEXT_LIMIT,
    format_lat_lng,
    format_speed,
    truncate,
)
from minitest_cli.commands.recording_action_parse import (
    as_int,
    as_number,
    as_str,
    is_curved,
    network_condition,
    pointer_point,
    route_of,
    target_name,
)


def _pointer(action: dict[str, Any]) -> str | None:
    verb = POINTER_VERBS[action["type"]]
    name = target_name(action)
    if name:
        return f"{verb} on “{truncate(name, TARGET_LIMIT)}”"
    point = pointer_point(action)
    return f"{verb} at ({point[0]}, {point[1]})" if point else None


def _text(action: dict[str, Any]) -> str | None:
    text = truncate(as_str(action.get("text")) or "", TEXT_LIMIT)
    if not text:
        return None
    name = target_name(action)
    return f"Type into “{truncate(name, TARGET_LIMIT)}”: “{text}”" if name else f"Type “{text}”"


def _network(action: dict[str, Any]) -> str | None:
    change = action.get("networkChange")
    if isinstance(change, str) and change in NETWORK_CHANGES:
        return NETWORK_CHANGES[change]
    condition = network_condition(action)
    if condition:
        return NETWORK_CONDITION_LABELS[condition]
    raw = as_str(action.get("networkCondition"))
    return f"Network · {raw}" if raw else None


def _route(action: dict[str, Any]) -> str:
    stops = [format_lat_lng(lat, lng) for lat, lng in route_of(action)]
    if len(stops) < 2:
        return "Simulating a route"
    parts = [f"Moving from {stops[0]} to {stops[-1]}"]
    if len(stops) > 2:
        count = len(stops) - 2
        parts.append(f"{count} waypoint{'' if count == 1 else 's'}")
    speed = as_number(action.get("speedMps"))
    if speed is not None and speed > 0:
        parts.append(f"{format_speed(speed)} m/s")
    return " · ".join(parts)


def _location(action: dict[str, Any]) -> str | None:
    mode = action.get("locationMode")
    if mode == "clear":
        return "Restoring real location"
    if mode == "route":
        return _route(action)
    lat, lng = as_number(action.get("latitude")), as_number(action.get("longitude"))
    return (
        f"Setting location to {format_lat_lng(lat, lng)}"
        if lat is not None and lng is not None
        else None
    )


def _backend(action: dict[str, Any]) -> str | None:
    url = as_str(action.get("url"))
    if not url:
        return None
    path = re.sub(r"^https?://[^/]+", "", url) or "/"
    call = f"{as_str(action.get('method')) or 'GET'} {path}"
    status = as_int(action.get("statusCode"))
    outcome = str(status) if status else ("failed" if action.get("error") else None)
    return f"{call} · {outcome}" if outcome else call


def _described(prefix: str, key: str) -> Callable[[dict[str, Any]], str | None]:
    def build(action: dict[str, Any]) -> str | None:
        value = as_str(action.get(key))
        return f"{prefix} · {value}" if value else None

    return build


DETAILED: dict[str, Callable[[dict[str, Any]], str | None]] = {
    "tap": _pointer,
    "long_press": _pointer,
    "click": _pointer,
    "text": _text,
    "network": _network,
    "orientation": lambda action: ORIENTATIONS.get(as_str(action.get("orientation")) or ""),
    "location": _location,
    "backend": _backend,
    "key": _described("Key", "description"),
    "nav": _described("Navigate", "url"),
}


def action_label(action: dict[str, Any]) -> str:
    """``Tap on “Sign in”``, ``Wi-Fi off``, ``POST /api/bets · 201``…"""
    action_type = action.get("type")
    if not isinstance(action_type, str):
        return "unknown"
    if is_curved(action):
        return "Curved gesture"
    if action_type not in FALLBACKS:
        return action_type
    build = DETAILED.get(action_type)
    return (build(action) if build else None) or FALLBACKS[action_type]
