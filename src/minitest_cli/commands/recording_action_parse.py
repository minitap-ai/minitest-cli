"""Defensive readers for the raw, camelCase agent actions of a run's trace.

The trace is written by testing-service and may come from older or newer
producers, so every reader ignores wrong types and non-finite numbers instead
of failing. Semantics mirror webapp-minitest ``lib/utils/agent-action-*.ts``.
"""

import math
from typing import Any

PLACEHOLDER_RADIUS = 4
POINTER_TYPES = frozenset({"tap", "long_press", "click"})

NETWORK_CONDITIONS = {
    "airplane_mode": "airplane_mode",
    "degraded": "degraded",
    "normal": "normal",
    "offline": "offline",
    # Legacy throttle presets written by older producers.
    "ultra_slow": "degraded",
    "slow": "degraded",
    "medium": "degraded",
    "full": "normal",
}

Point = tuple[float, float]


def as_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def non_empty(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def as_number(value: Any) -> float | None:
    """A finite JSON number; booleans are not numbers here."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return value if math.isfinite(value) else None


def as_int(value: Any) -> int | None:
    number = as_number(value)
    return int(number) if number is not None and float(number).is_integer() else None


def js_round(value: float) -> int:
    """``Math.round``: halves go toward +infinity."""
    return math.floor(value + 0.5)


def target_of(action: dict[str, Any]) -> dict[str, Any]:
    target = action.get("target")
    return target if isinstance(target, dict) else {}


def target_name(action: dict[str, Any]) -> str | None:
    """Human name of the addressed element: its label, else its identifier."""
    target = target_of(action)
    return non_empty(target.get("label")) or non_empty(target.get("identifier"))


def _pair(value: Any) -> Point | None:
    if not isinstance(value, list | tuple) or len(value) != 2:
        return None
    first, second = as_number(value[0]), as_number(value[1])
    return (first, second) if first is not None and second is not None else None


def _pairs(value: Any) -> list[Point]:
    if not isinstance(value, list):
        return []
    return [pair for pair in map(_pair, value) if pair is not None]


def points_of(action: dict[str, Any]) -> list[Point]:
    """Well-formed ``[x, y]`` points; malformed entries are dropped."""
    return _pairs(action.get("points"))


def route_of(action: dict[str, Any]) -> list[Point]:
    """Well-formed ``[lat, lng]`` route stops; malformed entries are dropped."""
    return _pairs(action.get("route"))


def pointer_point(action: dict[str, Any]) -> tuple[int, int] | None:
    """Where a pointer action landed, or None for the near-origin placeholder."""
    points = points_of(action)
    if not points or any(
        abs(x) <= PLACEHOLDER_RADIUS and abs(y) <= PLACEHOLDER_RADIUS for x, y in points
    ):
        return None
    return js_round(points[0][0]), js_round(points[0][1])


def is_curved(action: dict[str, Any]) -> bool:
    """A swipe or drag through intermediate waypoints traced a curve."""
    return action.get("type") in ("swipe", "drag") and len(points_of(action)) > 2


def network_condition(action: dict[str, Any]) -> str | None:
    value = action.get("networkCondition")
    return NETWORK_CONDITIONS.get(value) if isinstance(value, str) else None
