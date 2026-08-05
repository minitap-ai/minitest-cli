"""Human-readable rendering of httpx transport failures."""

import httpx

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

ALREADY_SENT_WARNING = (
    "The request reached the server before the client gave up, so it may well have "
    "been applied. Re-read the current state before retrying — a blind retry can "
    "duplicate the change."
)


def _request_of(exc: httpx.HTTPError) -> httpx.Request | None:
    if not isinstance(exc, httpx.RequestError):
        return None
    try:
        return exc.request
    except RuntimeError:
        return None


def format_network_error(exc: httpx.HTTPError, *, action: str | None = None) -> str:
    """Describe a transport failure, never collapsing to an empty message.

    ``str(exc)`` is empty for the timeouts httpx raises most often, which used to
    render as a bare ``Network error:`` telling the caller nothing.
    """
    label = f"Network error {action}" if action else "Network error"
    reason = str(exc).strip() or type(exc).__name__

    request = _request_of(exc)
    if request is None:
        return f"{label}: {reason}"

    method = request.method.upper()
    message = f"{label}: {reason} ({method} {request.url})"
    if isinstance(exc, httpx.ReadTimeout | httpx.WriteTimeout) and method not in SAFE_METHODS:
        return f"{message}. {ALREADY_SENT_WARNING}"
    return message
