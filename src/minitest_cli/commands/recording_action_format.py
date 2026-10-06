"""English copy and formatting for action labels, matching webapp-minitest.

Mirrors ``lib/utils/agent-action-format.ts``: ``truncateLabelText``,
``formatCoordinate`` (``toFixed(6)`` then shortest form) and the English
``Intl.NumberFormat`` speed with at most one decimal; the copy is ``messages/en.json``.
"""

import re
from decimal import ROUND_HALF_UP, Context, Decimal

TEXT_LIMIT = 40
TARGET_LIMIT = 24
FALLBACKS = {
    "tap": "Tap",
    "long_press": "Long press",
    "click": "Click",
    "swipe": "Swipe",
    "drag": "Drag",
    "pinch": "Pinch",
    "scroll": "Scroll",
    "key": "Key",
    "nav": "Navigate",
    "network": "Network",
    "orientation": "Rotate",
    "location": "Location change",
    "text": "Type text",
    "backend": "Backend call",
}
POINTER_VERBS = {"tap": "Tap", "long_press": "Long press", "click": "Click"}
NETWORK_CHANGES = {
    "airplane_mode_on": "Airplane mode on",
    "airplane_mode_off": "Airplane mode off",
    "wifi_off": "Wi-Fi off",
    "wifi_on": "Wi-Fi on",
    "offline": "Network offline",
    "online": "Network online",
}
NETWORK_CONDITION_LABELS = {
    "airplane_mode": "Airplane mode",
    "degraded": "Network degraded",
    "normal": "Network normal",
    "offline": "Network offline",
}
ORIENTATIONS = {"landscape": "Rotate to landscape", "portrait": "Rotate to portrait"}
# Exact float → decimal conversion, rounding ties away from zero like ``toFixed``.
_WIDE = Context(prec=400, rounding=ROUND_HALF_UP)


def truncate(value: str, limit: int) -> str:
    """Whitespace collapsed; cut text ends with a real ellipsis."""
    flat = re.sub(r"\s+", " ", value).strip()
    return flat if len(flat) <= limit else f"{flat[: limit - 1].rstrip()}…"


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    text = text.rstrip("0").rstrip(".") if "." in text else text
    return "0" if text in ("-0", "") else text


def format_coordinate(value: float) -> str:
    """At most 6 decimals, trailing zeros stripped, always a dot separator."""
    return _decimal_text(_WIDE.quantize(Decimal(value), Decimal("0.000001")))


def format_lat_lng(lat: float, lng: float) -> str:
    return f"{format_coordinate(lat)}, {format_coordinate(lng)}"


def format_speed(value: float) -> str:
    """At most one decimal, thousands grouped, as ``Intl.NumberFormat('en')``."""
    rounded = _WIDE.quantize(Decimal(value), Decimal("0.1"))
    whole, _, fraction = _decimal_text(rounded).partition(".")
    return f"{int(whole):,}" + (f".{fraction}" if fraction else "")
