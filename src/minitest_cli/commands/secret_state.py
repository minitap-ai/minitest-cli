"""A secret's state: set (typed or generated) or missing (waiting for a human's value)."""

from typing import Any


def has_value(secret: dict[str, Any]) -> bool:
    """Servers before secrets without a value omit ``hasValue``: every secret had one."""
    return secret.get("hasValue") is not False


def state(secret: dict[str, Any]) -> str:
    if has_value(secret):
        return "generated" if secret.get("valueOrigin") == "generated" else "set"
    reason = secret.get("pendingReason")
    return f"missing: {reason}" if reason else "missing"


def request_rows(requests: list[dict[str, Any]]) -> list[list[str]]:
    return [
        [
            r.get("name", ""),
            r.get("kind", ""),
            r.get("storyName") or r.get("storyId") or "",
            r.get("requestedBy", ""),
            r.get("reason", ""),
        ]
        for r in requests
    ]


def secret_rows(secrets: list[dict[str, Any]]) -> list[list[str]]:
    return [
        [
            s.get("name", ""),
            s.get("kind", ""),
            state(s),
            str(s.get("version") or "-") if has_value(s) else "-",
            str(len(s.get("usages") or [])),
            s.get("note") or "",
        ]
        for s in sorted(secrets, key=has_value)
    ]
