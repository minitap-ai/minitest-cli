"""`minitest targets catalog` against a fake catalog and farm inventory."""

import json

import httpx
from typer.testing import CliRunner

from minitest_cli.commands import targets_catalog
from tests._commit_transport import cli_context, make_settings, routed

runner = CliRunner()

CATALOG = {
    "cloud": [
        {"platform": "ios", "formFactor": "phone", "label": "iPhone", "osVersions": ["26", "27"],
         "defaultOsVersion": "26", "available": True},
        {"platform": "ios", "formFactor": "duo", "label": "iPhone Duo", "osVersions": ["27"],
         "defaultOsVersion": "27", "available": False,
         "unavailableReason": "iPhone Duo is not supported by Minitest yet."},
    ],
    "physical": {"inventoryPath": "/api/v1/farm/inventory"},
    "web": [
        {"browser": "chrome", "screens": ["pc", "tablet", "mobile"], "versions": ["157", "156"],
         "defaultVersion": "157", "noStealthVersions": ["156"]},
        {"browser": "safari", "screens": ["mobile"], "versions": [], "defaultVersion": None},
    ],
}  # fmt: skip
INVENTORY = {
    "generatedAt": "2026-11-06T10:00:00Z",
    "platforms": [
        {"platform": "ios", "total": 2, "availableNow": 1,
         "models": [{"model": "iPhone 13", "osVersions": ["18.7"], "total": 2, "availableNow": 1}]},
    ],
}  # fmt: skip


TENANT = "8fdc0ac6-d419-495d-9cae-2dc27653a34a"


def _handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/api/v1/tenants":
        return httpx.Response(200, json=[{"id": TENANT, "name": "Minitap"}])
    if request.url.path == "/api/v1/targets/catalog":
        assert request.url.params["tenant_id"] == TENANT
        return httpx.Response(200, json=CATALOG)
    assert request.url.path == "/api/v1/farm/inventory"
    return httpx.Response(200, json=INVENTORY)


def _invoke(tmp_path, *, json_mode: bool):
    settings = make_settings(tmp_path, app_id=None)
    with cli_context(settings, json_mode=json_mode), routed(_handler):
        return runner.invoke(targets_catalog.app, [], env={"COLUMNS": "200"})


class TestCatalog:
    def test_every_row_says_how_to_ask_for_it(self, tmp_path):
        result = _invoke(tmp_path, json_mode=False)

        assert result.exit_code == 0, result.output
        out = " ".join(result.output.split())
        assert "26 (default), 27" in out
        assert "platform=ios,os=26" in out
        assert "iPhone Duo is not supported by Minitest yet." in out
        assert '"platform=ios,backend=physical,model=iPhone 13"' in out
        assert "1 of 2" in out
        assert "157, 156 (no stealth)" in out
        assert "platform=web,browser=chrome,version=157" in out
        assert "safari" not in out

    def test_json_carries_the_farm_models(self, tmp_path):
        result = _invoke(tmp_path, json_mode=True)

        assert result.exit_code == 0, result.output
        data = json.loads(result.stdout)
        assert data["physical"][0]["models"][0]["model"] == "iPhone 13"
        assert data["web"][0]["versions"] == ["157", "156"]
        assert data["app"] is None
        assert data["tenantId"] == TENANT


APP = "a0d9820f-5136-4f70-b46b-e5966f56bfb5"


def _app_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/api/v1/apps":
        return httpx.Response(
            200, json={"apps": [{"id": APP, "name": "Molotov", "tenantId": TENANT}]}
        )
    if path == f"/api/v1/tenants/{TENANT}/apps/{APP}":
        detail = {"id": APP, "tenantId": TENANT, "name": "Molotov", "slug": "molotov"}
        return httpx.Response(200, json={**detail, "platforms": ["android"], "formFactor": "tv"})
    if path == "/api/v1/targets/catalog":
        return httpx.Response(200, json=CATALOG)
    assert path == f"/api/v1/apps/{APP}/physical-devices"
    stock = {"platforms": [{**INVENTORY["platforms"][0], "platform": "android"}]}
    return httpx.Response(
        200,
        json={"available": True, "platforms": {"ios": True, "android": True},
              "farmReachable": True, "inventory": stock},
    )  # fmt: skip


class TestAppCatalog:
    def test_a_tv_app_runs_on_android_tv_and_reads_the_app_farm_view(self, tmp_path):
        with cli_context(make_settings(tmp_path), json_mode=False), routed(_app_handler):
            result = runner.invoke(targets_catalog.app, [], env={"COLUMNS": "200"})

        assert result.exit_code == 0, result.output
        out = " ".join(result.output.split())
        assert "platform=android,device=tv" in out
        assert "Android phone" not in out
        assert "iPhone ·" not in out and "platform=ios" not in out
