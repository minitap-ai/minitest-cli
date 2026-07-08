"""API helpers for the maintenance command group.

The maintenance flow spans several CLI invocations driven by the customer's own
coding agent. ``context`` opens a run and persists a handle (run id + token) so the
follow-up subcommands can post back without threading the token through each call.
"""

import hashlib
import json
from typing import Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.core.config import Settings
from minitest_cli.models.app import AppListResponse
from minitest_cli.utils.output import print_error

EXIT_NETWORK_ERROR = 3
EXIT_NOT_FOUND = 4

CALLBACK_BASE = "/api/v1/internal/maintenance-runs"
CLI_RUNS_PATH = "/api/v1/maintenance/cli/runs"
REASONING_PATH = "/api/v1/maintenance/cli/reasoning"
APPLY_PENDING_PATH = "/api/v1/maintenance/cli/apps/{app_id}/apply-pending"


async def fetch_reasoning(settings: Settings) -> str:
    """Fetch the composed CLI-maintenance reasoning document (tenant-authed)."""
    async with ApiClient(settings) as client:
        resp = await client.get(REASONING_PATH)
    if resp.status_code >= 400:
        print_error(f"Could not fetch maintenance reasoning: {resp.status_code}")
        raise typer.Exit(code=EXIT_NETWORK_ERROR)
    return resp.text


async def open_run(settings: Settings, app_id: str, head_sha: str) -> dict[str, Any]:
    """Open a CLI maintenance run (tenant-authed); returns the run handle payload."""
    async with ApiClient(settings) as client:
        resp = await client.post(
            CLI_RUNS_PATH,
            json={"appId": app_id, "headCommitSha": head_sha},
        )
    if resp.status_code >= 400:
        _fail(resp)
    return resp.json()


async def fetch_context(settings: Settings, run_id: str, token: str) -> dict[str, Any]:
    """Fetch the maintenance /context payload with the run token."""
    async with ApiClient(settings, token_override=token) as client:
        resp = await client.get(f"{CALLBACK_BASE}/{run_id}/context")
    if resp.status_code >= 400:
        _fail(resp)
    return resp.json()


async def post_callback(
    settings: Settings,
    run_id: str,
    token: str,
    sub_path: str,
    payload: dict[str, Any],
    idempotency_key: str | None = None,
) -> dict[str, Any] | None:
    """POST a payload to a token-authed run callback endpoint."""
    headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
    async with ApiClient(settings, token_override=token) as client:
        resp = await client.post(
            f"{CALLBACK_BASE}/{run_id}/{sub_path}",
            json=payload,
            headers=headers,
        )
    if resp.status_code >= 400:
        _fail(resp)
    return resp.json() if resp.content else None


async def complete_run(settings: Settings, run_id: str, *, changed: bool) -> None:
    """Mark the run complete (tenant-authed); advances the watermark only when changed."""
    async with ApiClient(settings) as client:
        resp = await client.post(
            f"{CLI_RUNS_PATH}/{run_id}/complete",
            json={"changed": changed},
        )
    if resp.status_code >= 400:
        _fail(resp)


async def apply_pending(settings: Settings, app_id: str) -> dict[str, Any]:
    """Apply pending maintenance changes for the app (tenant-authed)."""
    async with ApiClient(settings) as client:
        resp = await client.post(APPLY_PENDING_PATH.format(app_id=app_id), json={})
    if resp.status_code >= 400:
        _fail(resp)
    return resp.json()


async def fetch_app_tenant(settings: Settings, app_id: str) -> str:
    """Resolve the tenant that owns the app so review links target the right tenant."""
    async with ApiClient(settings) as client:
        resp = await client.get("/api/v1/apps")
    if resp.status_code >= 400:
        _fail(resp)
    for app in AppListResponse.model_validate(resp.json()).apps:
        if app.id == app_id:
            return app.tenant_id
    print_error(f"App not found: {app_id}")
    raise typer.Exit(code=EXIT_NOT_FOUND)


def review_queue_url(settings: Settings, app_id: str, tenant: str) -> str:
    """Return the tenant-scoped Release Queue URL for manual review."""
    return f"{settings.webapp_url}/t/{tenant}/apps/{app_id}/test/queue"


def change_idempotency_key(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()


def _fail(resp: Any) -> None:
    detail = None
    try:
        body = resp.json()
        if isinstance(body, dict):
            detail = body.get("detail") or body.get("message")
    except Exception:  # noqa: BLE001
        pass
    print_error(detail or f"API error: {resp.status_code}")
    raise typer.Exit(code=EXIT_NETWORK_ERROR)
