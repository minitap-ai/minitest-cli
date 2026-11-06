"""`minitest targets catalog`: the devices, OS versions and browsers a run can ask for."""

from typing import Annotated, Any

import httpx
import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands._response_errors import extract_detail
from minitest_cli.commands.apps_helpers import get_app_request
from minitest_cli.commands.env_helpers import resolve_app_and_tenant
from minitest_cli.commands.run_helpers import handle_response_error, run_api_call
from minitest_cli.commands.targets_catalog_display import print_catalog
from minitest_cli.commands.user_story_helpers import get_app_flag, get_settings, is_json_mode
from minitest_cli.core.auth import require_auth
from minitest_cli.core.config import Settings
from minitest_cli.core.tenants import fetch_user_tenants, resolve_tenant_id
from minitest_cli.utils.output import output

app = typer.Typer(name="targets", help="What a run can target: devices, OS versions, browsers.")

CATALOG_PATH = "/api/v1/targets/catalog"
FARM_INVENTORY_PATH = "/api/v1/farm/inventory"
PHYSICAL_DEVICES_PATH = "/api/v1/apps/{app_id}/physical-devices"


TenantOpt = Annotated[
    str | None,
    typer.Option("--tenant", help="Workspace ID; defaults to the --app's, else your only one."),
]


async def _app_scope(settings: Settings) -> tuple[str, dict[str, Any]] | None:
    if not (get_app_flag() or settings.app_id):
        return None
    app_id, tenant_id = await resolve_app_and_tenant(settings, get_app_flag())
    detail = await get_app_request(settings, tenant_id=tenant_id, app_id=app_id)
    extra = detail.model_extra or {}
    scope = {
        "id": detail.id,
        "name": detail.name,
        "platforms": detail.platforms,
        "formFactor": extra.get("formFactor", extra.get("form_factor")),
    }
    return tenant_id, scope


def _physical(resp: httpx.Response, *, app_scoped: bool) -> dict[str, Any]:
    """Farm models as the launcher lists them: the app's view when there is an app."""
    if resp.status_code != 200:
        return {"physical": [], "physicalUnavailable": extract_detail(resp)}
    body = resp.json()
    if not app_scoped:
        return {"physical": body.get("platforms", [])}
    enabled = body.get("platforms") or {}
    stock = (body.get("inventory") or {}).get("platforms", [])
    physical = [p for p in stock if enabled.get(p.get("platform"))]
    if not body.get("available"):
        return {"physical": [], "physicalUnavailable": "not enabled for this workspace"}
    if not body.get("farmReachable", True):
        return {"physical": [], "physicalUnavailable": "the device farm did not answer"}
    return {"physical": physical}


async def _fetch(settings: Settings, tenant: str | None) -> dict[str, Any]:
    scoped = None if tenant else await _app_scope(settings)
    if scoped is not None:
        tenant = scoped[0]
    elif tenant is None:
        tenant = resolve_tenant_id(settings, None, await fetch_user_tenants(settings))
    async with ApiClient(settings) as client:
        resp = await client.get(CATALOG_PATH, params={"tenant_id": tenant})
        handle_response_error(resp, resource="Target catalog")
        catalog: dict[str, Any] = resp.json()
        if scoped is not None:
            farm = await client.get(PHYSICAL_DEVICES_PATH.format(app_id=scoped[1]["id"]))
        else:
            farm = await client.get(
                catalog.get("physical", {}).get("inventoryPath") or FARM_INVENTORY_PATH
            )
    catalog.update(_physical(farm, app_scoped=scoped is not None))
    catalog["tenantId"] = tenant
    catalog["app"] = scoped[1] if scoped else None
    return catalog


@app.command(name="catalog")
def catalog(tenant: TenantOpt = None) -> None:
    """List cloud devices with their OS versions, the farm's physical models, and browser versions.

    Pass --app to scope it to one app's platforms (a TV app runs on Android TV only).
    """
    settings = get_settings()
    require_auth(settings)
    data = run_api_call(_fetch(settings, tenant))
    if is_json_mode():
        output(data, json_mode=True)
        return
    print_catalog(data)
