"""Helpers for env-var commands: app/tenant resolution, HTTP, confirmation."""

import sys

import httpx
import typer

from minitest_cli.api.apps_manager_client import AppsManagerClient
from minitest_cli.api.client import ApiClient
from minitest_cli.core.config import Settings
from minitest_cli.models.app import AppListResponse
from minitest_cli.models.app_env_vars import AppEnvVarsResponse
from minitest_cli.utils.output import print_error

EXIT_GENERAL_ERROR = 1
EXIT_NETWORK_ERROR = 3
EXIT_NOT_FOUND = 4

MASK = "********"


def env_vars_path(tenant_id: str, app_id: str) -> str:
    return f"/api/v1/tenants/{tenant_id}/apps/{app_id}/env-vars"


async def resolve_app_and_tenant(settings: Settings, app_flag: str | None) -> tuple[str, str]:
    """Resolve ``--app`` (id or name) to a concrete ``(app_id, tenant_id)`` pair.

    The env-vars endpoint verifies the app belongs to the tenant, so both ids
    must come from the same app record.
    """
    target = app_flag or settings.app_id
    if not target:
        print_error("No app specified. Use --app <id-or-name> or set MINITEST_APP_ID.")
        raise typer.Exit(code=EXIT_GENERAL_ERROR)

    async with ApiClient(settings) as client:
        resp = await client.get("/api/v1/apps")
    if resp.status_code >= 400:
        print_error(f"API error ({resp.status_code}): failed to list apps.")
        raise typer.Exit(code=EXIT_NETWORK_ERROR)

    apps = AppListResponse.model_validate(resp.json()).apps
    lowered = target.lower()
    matches = [a for a in apps if a.id == target or a.name.lower() == lowered]
    if not matches:
        print_error(f"App not found: '{target}'. Use a valid app id or name.")
        raise typer.Exit(code=EXIT_NOT_FOUND)
    if len(matches) > 1:
        print_error(f"Ambiguous app name '{target}' matches {len(matches)} apps. Use the app id.")
        raise typer.Exit(code=EXIT_GENERAL_ERROR)

    app = matches[0]
    return app.id, app.tenant_id


async def fetch_env_vars(settings: Settings, tenant_id: str, app_id: str) -> dict[str, str]:
    """Return the app's env vars, or an empty dict when none are configured (404)."""
    async with AppsManagerClient(settings) as client:
        resp = await client.get(env_vars_path(tenant_id, app_id))
    if resp.status_code == 404:
        return {}
    _raise_for_status(resp, resource="Environment variables")
    return AppEnvVarsResponse.model_validate(resp.json()).env_vars


async def put_env_vars(
    settings: Settings, tenant_id: str, app_id: str, env_vars: dict[str, str]
) -> AppEnvVarsResponse:
    """Replace the app's full env-var set."""
    async with AppsManagerClient(settings) as client:
        resp = await client.put(env_vars_path(tenant_id, app_id), json={"envVars": env_vars})
    _raise_for_status(resp, resource="Environment variables")
    return AppEnvVarsResponse.model_validate(resp.json())


async def delete_env_vars(settings: Settings, tenant_id: str, app_id: str) -> None:
    """Delete all env vars for the app."""
    async with AppsManagerClient(settings) as client:
        resp = await client.delete(env_vars_path(tenant_id, app_id))
    if resp.status_code == 404:
        print_error("No environment variables to delete.")
        raise typer.Exit(code=EXIT_NOT_FOUND)
    _raise_for_status(resp, resource="Environment variables")


def _raise_for_status(resp: httpx.Response, *, resource: str) -> None:
    if resp.status_code < 400:
        return
    detail = _extract_detail(resp)
    if resp.status_code == 404:
        print_error(detail or f"{resource} not found.")
        raise typer.Exit(code=EXIT_NOT_FOUND)
    if resp.status_code >= 500:
        print_error(detail or f"API error: {resp.status_code}")
        raise typer.Exit(code=EXIT_NETWORK_ERROR)
    print_error(detail or f"API error: {resp.status_code}")
    raise typer.Exit(code=EXIT_GENERAL_ERROR)


def _extract_detail(resp: httpx.Response) -> str | None:
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        return None
    if isinstance(body, dict):
        return body.get("detail") or body.get("message")
    return None


def confirm_or_exit(yes: bool, action: str) -> None:
    """Gate a mutating action behind explicit confirmation.

    Passing ``--yes`` proceeds. Without it we refuse rather than prompt, so the
    command stays safe to run non-interactively (agents/CI) — exit 1 naming the
    flag that unblocks it.
    """
    if yes:
        return
    print_error(f"{action} requires confirmation. Re-run with --yes to proceed.")
    raise typer.Exit(code=EXIT_GENERAL_ERROR)


def diff_keys(
    current: dict[str, str], updated: dict[str, str]
) -> tuple[list[str], list[str], list[str]]:
    """Return (added, changed, removed) keys between two env-var maps."""
    added = sorted(k for k in updated if k not in current)
    removed = sorted(k for k in current if k not in updated)
    changed = sorted(k for k in updated if k in current and updated[k] != current[k])
    return added, changed, removed


def print_diff(added: list[str], changed: list[str], removed: list[str]) -> None:
    for key in added:
        print(f"+ {key}", file=sys.stderr)  # noqa: T201
    for key in changed:
        print(f"~ {key}", file=sys.stderr)  # noqa: T201
    for key in removed:
        print(f"- {key}", file=sys.stderr)  # noqa: T201
