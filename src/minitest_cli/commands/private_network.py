"""'apps private-network': reach a customer's internal domains through a connector."""

from typing import Annotated, Any

import typer

from minitest_cli.commands.app_network_helpers import (
    call_api,
    fail,
    is_json_mode,
    merge_domains,
    resolve_target,
)
from minitest_cli.commands.private_network_helpers import (
    CREATE_IN_WEBAPP_HINT,
    UNAVAILABLE_MESSAGE,
    render_config,
    render_connectors,
    resolve_connector,
)
from minitest_cli.core.config import Settings
from minitest_cli.utils.output import print_success

app = typer.Typer(
    name="private-network",
    help=(
        "Private network of the app (--app): devices reach internal domains through a "
        "connector running in your network. Changing it needs the OWNER or ADMIN role. "
        f"{CREATE_IN_WEBAPP_HINT}"
    ),
    no_args_is_help=True,
)


def _path(app_id: str) -> str:
    return f"/api/v1/apps/{app_id}/private-network"


@app.command(name="show")
def show() -> None:
    """Show the app's private network settings."""
    settings, app_id = resolve_target()
    config = call_api(settings, "GET", _path(app_id))
    render_config(config)


@app.command(name="connectors")
def connectors() -> None:
    """List the workspace connectors the app can route through (read-only)."""
    settings, app_id = resolve_target()
    listing = call_api(settings, "GET", f"{_path(app_id)}/connectors")
    render_connectors(listing)


@app.command(name="set")
def set_config(
    enable: Annotated[
        bool | None,
        typer.Option(
            "--enable/--disable",
            help="Switch it on or off. On needs a connector and at least one domain.",
        ),
    ] = None,
    connector: Annotated[
        str | None,
        typer.Option("--connector", help="Connector name or id (see 'connectors')."),
    ] = None,
    domain: Annotated[
        list[str] | None,
        typer.Option(
            "--domain",
            help="Internal domain to reach (repeatable): host, or *.host for its subdomains only.",
        ),
    ] = None,
    remove_domain: Annotated[
        list[str] | None,
        typer.Option("--remove-domain", help="Domain to stop reaching (repeatable)."),
    ] = None,
    clear_domains: Annotated[
        bool,
        typer.Option("--clear-domains", help="Drop every current domain before adding --domain."),
    ] = False,
    port: Annotated[
        list[int] | None,
        typer.Option(
            "--port",
            min=1,
            max=65535,
            help="Port devices may reach (repeatable). Replaces the current ports; default 443.",
        ),
    ] = None,
) -> None:
    """Change the app's private network settings; options not passed stay as they are."""
    if not any([enable is not None, connector, domain, remove_domain, clear_domains, port]):
        raise fail(
            "Nothing to change: pass --enable/--disable, --connector, a domain option or --port."
        )
    settings, app_id = resolve_target()
    current = call_api(settings, "GET", _path(app_id))
    body = _build_body(settings, app_id, current, enable, connector, port)
    body["domains"] = merge_domains(
        current["domains"],
        add=domain,
        remove=remove_domain,
        clear=clear_domains,
        pattern=current["domainPattern"],
        max_domains=current["maxDomains"],
    )
    if body["enabled"]:
        if not current["available"]:
            raise fail(UNAVAILABLE_MESSAGE)
        if not body["connectorId"]:
            raise fail(
                "Turning it on needs a connector: pass --connector <name-or-id> "
                f"(see 'minitest apps private-network connectors'). {CREATE_IN_WEBAPP_HINT}"
            )
        if not body["domains"]:
            raise fail("Turning it on needs at least one --domain.")

    updated = call_api(settings, "PUT", _path(app_id), body)
    if not is_json_mode():
        print_success("Private network updated.")
    render_config(updated)


def _build_body(
    settings: Settings,
    app_id: str,
    current: dict[str, Any],
    enable: bool | None,
    connector: str | None,
    port: list[int] | None,
) -> dict[str, Any]:
    if connector:
        listing = call_api(settings, "GET", f"{_path(app_id)}/connectors")
        connector_id = resolve_connector(listing["connectors"], connector)["id"]
    else:
        connector_id = current["connector"]["id"] if current["connector"] else None
    return {
        "enabled": current["enabled"] if enable is None else enable,
        "connectorId": connector_id,
        "ports": list(dict.fromkeys(port)) if port else current["ports"] or [443],
    }
