"""Shared HTTP response error handling for build/run commands.

Split out of ``build_helpers.py`` so the file-length gate stays comfortable
as we add per-error pretty renderers (currently: ``build_invalid`` and
``split_apks_backend_unsupported``).
"""

import httpx
import typer

from minitest_cli.utils.output import err_console, print_error

EXIT_NETWORK_ERROR = 3
EXIT_NOT_FOUND = 4
EXIT_BUILD_INVALID = 5

BUILD_INVALID_ERROR_CODE = "build_invalid"

# Substring the testing-service ``SplitApksBackendUnsupportedError`` puts in
# its 422 detail. Matched here so the CLI can render an actionable message
# (with a bundletool hint) instead of the generic ``API error (422): ...``.
# The error is raised at batch dispatch when a ``.apks`` archive lands on a
# backend that cannot install split APKs (today: EDGE; before the CLOUD
# rollout: both).
_SPLIT_APKS_BACKEND_UNSUPPORTED_MARKER = "not yet supported on this execution backend"

# Generic FastAPI ``loc`` prefixes that add noise to a field path (they're
# implied by "this is a validation error" and repeat across every field).
_LOC_PREFIXES_TO_DROP = {"body", "query", "path"}


def format_validation_field_errors(body: object) -> str | None:
    """Render a validation-error body as ``field: message`` lines.

    Handles both the stock FastAPI shape (``detail`` as a list of
    ``{"loc": [...], "msg": ...}`` dicts) and the shared
    ``minitap_observability`` exception-handler shape (``details.errors`` as a
    list of ``{"field": ..., "message": ...}`` dicts) — the latter puts only a
    generic ``"Request validation failed"`` in the top-level ``message``, so
    without this the CLI would otherwise discard the actually useful part.
    Returns ``None`` if ``body`` isn't a validation-error envelope of either shape.
    """
    if not isinstance(body, dict):
        return None
    raw_errors = _extract_raw_field_errors(body)
    if not raw_errors:
        return None
    return "; ".join(_format_field_error(loc, msg) for loc, msg in raw_errors)


def _extract_raw_field_errors(body: dict) -> list[tuple[list[str], str]] | None:
    detail = body.get("detail")
    if isinstance(detail, list) and detail:
        return [
            ([str(p) for p in e.get("loc", [])], str(e.get("msg", "")))
            for e in detail
            if isinstance(e, dict)
        ]
    details = body.get("details")
    if isinstance(details, dict):
        nested = details.get("errors")
        if isinstance(nested, list) and nested:
            return [
                (str(e.get("field", "")).split("."), str(e.get("message", "")))
                for e in nested
                if isinstance(e, dict)
            ]
    return None


def _format_field_error(loc: list[str], msg: str) -> str:
    field = ".".join(part for part in loc if part and part not in _LOC_PREFIXES_TO_DROP)
    return f"{field}: {msg}" if field else msg


def extract_detail(resp: httpx.Response) -> str:
    """Extract a human-readable error detail from an API response."""
    try:
        body = resp.json()
        if isinstance(body, dict):
            field_errors = format_validation_field_errors(body)
            if field_errors is not None:
                return field_errors
        return str(body.get("detail", body.get("message", resp.text)))
    except Exception:  # noqa: BLE001
        return resp.text


def handle_response_error(resp: httpx.Response, *, resource: str = "Build") -> None:
    """Check response status; exit with proper code on errors."""
    if resp.status_code == 404:
        print_error(f"{resource} not found: {extract_detail(resp)}")
        raise typer.Exit(code=EXIT_NOT_FOUND)
    if resp.status_code == 422 and _try_handle_split_apks_backend_unsupported(resp):
        raise typer.Exit(code=EXIT_BUILD_INVALID)
    if resp.status_code == 422 and _try_handle_build_invalid(resp):
        raise typer.Exit(code=EXIT_BUILD_INVALID)
    if resp.status_code >= 400:
        print_error(f"API error ({resp.status_code}): {extract_detail(resp)}")
        raise typer.Exit(code=EXIT_NETWORK_ERROR)


def _try_handle_split_apks_backend_unsupported(resp: httpx.Response) -> bool:
    """Render an actionable message for a rejected ``.apks`` batch dispatch.

    The testing-service ``SplitApksBackendUnsupportedError`` comes back as a
    plain 422 with a string ``detail`` (not the ``build_invalid`` envelope),
    so match on the marker substring. If the message ever drifts, this quietly
    falls back to the generic ``API error (422): ...`` output.
    """
    detail = extract_detail(resp)
    if _SPLIT_APKS_BACKEND_UNSUPPORTED_MARKER not in detail:
        return False
    print_error("Split APK archive (.apks) rejected before dispatch.")
    err_console.print(f"  [dim]Server said:[/dim] {detail}")
    err_console.print(
        "  [yellow]Fix:[/yellow] rebuild as a single universal APK "
        "(e.g. [bold]bundletool build-apks --mode=universal[/bold] then extract "
        "the .apk from the resulting .apks) and re-upload with "
        "[bold]minitest build upload[/bold]."
    )
    return True


def _try_handle_build_invalid(resp: httpx.Response) -> bool:
    """If response is a build-invalid error, render issues and return True."""
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        return False
    if not isinstance(body, dict) or body.get("error_code") != BUILD_INVALID_ERROR_CODE:
        return False
    issues = body.get("issues") or []
    print_error("Build rejected: failed validation for virtual-device execution.")
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        code = issue.get("code", "unknown")
        message = issue.get("message", "")
        err_console.print(f"  [red]✖[/red] {code}: {message}")
    return True


def print_validation_warnings(warnings: list[dict] | None) -> None:
    """Print non-fatal validation warnings to stderr."""
    if not warnings:
        return
    for warning in warnings:
        if not isinstance(warning, dict):
            continue
        code = warning.get("code", "unknown")
        message = warning.get("message", "")
        err_console.print(f"  [yellow]⚠[/yellow] {code}: {message}")
