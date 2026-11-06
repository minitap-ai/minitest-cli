"""Tables of `minitest targets catalog`, each row with the --target that asks for it."""

from typing import Any

from minitest_cli.commands.target_rules import BROWSERS
from rich.console import Console
from rich.table import Table

from minitest_cli.utils.output import err_console, print_info

_SCREENS = {"pc": "desktop", "tablet": "tablet", "mobile": "mobile"}


def _versions(versions: list[str], default: str | None) -> str:
    return ", ".join(f"{v} (default)" if v == default else v for v in versions) or "-"


def _scoped(platform: str, app: dict[str, Any] | None) -> bool:
    return app is None or not app.get("platforms") or platform in app["platforms"]


def _cloud_rows(catalog: dict[str, Any], app: dict[str, Any] | None) -> list[list[str]]:
    tv_app = bool(app and app.get("formFactor") == "tv")
    rows = []
    for device in catalog.get("cloud", []):
        platform, form = device["platform"], device["formFactor"]
        if not _scoped(platform, app) or (tv_app and platform == "android"):
            continue
        available = "yes" if device.get("available") else device.get("unavailableReason") or "no"
        spec = f"platform={platform}" + (f",device={form}" if form != "phone" else "")
        os = device.get("defaultOsVersion") or (device.get("osVersions") or [None])[-1]
        rows.append(
            [
                device["label"],
                _versions(device.get("osVersions", []), device.get("defaultOsVersion")),
                available,
                "-" if not device.get("available") else f"{spec},os={os}" if os else spec,
            ]
        )
    if tv_app:
        rows.append(["Android TV", "-", "yes", "platform=android,device=tv"])
    return rows


def _physical_rows(catalog: dict[str, Any], app: dict[str, Any] | None) -> list[list[str]]:
    tv_app = bool(app and app.get("formFactor") == "tv")
    rows = []
    for entry in catalog.get("physical", []):
        platform = entry.get("platform", "")
        if not _scoped(platform, app) or (tv_app and platform == "android"):
            continue
        for model in entry.get("models", []):
            name = model.get("model", "")
            rows.append(
                [
                    platform,
                    name,
                    ", ".join(model.get("osVersions", [])) or "-",
                    f"{model.get('availableNow', 0)} of {model.get('total', 0)}",
                    f'"platform={platform},backend=physical,model={name}"',
                ]
            )
    return rows


def _web_rows(catalog: dict[str, Any], app: dict[str, Any] | None) -> list[list[str]]:
    if not _scoped("web", app):
        return []
    rows = []
    for browser in catalog.get("web", []):
        name = browser["browser"]
        if name not in BROWSERS:
            continue
        screens = [_SCREENS.get(str(s), str(s)) for s in browser.get("screens", [])]
        versions = browser.get("versions", [])
        no_stealth = set(browser.get("noStealthVersions", []))
        shown = [f"{v} (no stealth)" if v in no_stealth else v for v in versions]
        spec = f"platform=web,browser={name}"
        if versions:
            spec += f",version={browser.get('defaultVersion') or versions[0]}"
        rows.append([name, ", ".join(screens), ", ".join(shown) or "default only", spec])
    return rows


def _print_table(headers: list[str], rows: list[list[str]]) -> None:
    """Folds instead of cutting, so a --target value is never shortened to an ellipsis."""
    table = Table(show_header=True, header_style="bold")
    for header in headers:
        table.add_column(header, overflow="fold")
    for row in rows:
        table.add_row(*row)
    Console().print(table)


def print_catalog(catalog: dict[str, Any]) -> None:
    app = catalog.get("app")
    if app:
        print_info(f"Targets for {app['name']} ({', '.join(app.get('platforms') or [])})")
    cloud = _cloud_rows(catalog, app)
    if cloud:
        _print_table(["Cloud device", "OS versions", "Available", "--target"], cloud)
    physical = _physical_rows(catalog, app)
    if physical:
        headers = ["Platform", "Physical model", "OS versions", "Free now", "--target"]
        _print_table(headers, physical)
    elif catalog.get("physicalUnavailable"):
        err_console.print(f"  Physical devices: {catalog['physicalUnavailable']}")
    web = _web_rows(catalog, app)
    if web:
        _print_table(["Browser", "Screens", "Versions", "--target"], web)
