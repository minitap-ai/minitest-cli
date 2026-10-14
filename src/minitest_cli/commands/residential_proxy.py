"""'apps residential-proxy': route some of an app's device traffic through residential IPs."""

from typing import Annotated, Any

import typer

from minitest_cli.commands.app_network_helpers import (
    call_api,
    domain_list,
    fail,
    is_json_mode,
    merge_domains,
    on_off,
    resolve_target,
)
from minitest_cli.utils.output import print_json, print_success, print_warning

app = typer.Typer(
    name="residential-proxy",
    help=(
        "Residential proxy of the app (--app): devices reach the listed domains from a "
        "residential IP in the chosen country. Changing it needs the OWNER or ADMIN role."
    ),
    no_args_is_help=True,
)

UNAVAILABLE_MESSAGE = (
    "This workspace cannot use the residential proxy. Contact Minitap to enable it."
)


def _path(app_id: str) -> str:
    return f"/api/v1/apps/{app_id}/residential-proxy"


def _render(config: dict[str, Any]) -> None:
    if not config["available"]:
        print_warning(UNAVAILABLE_MESSAGE)
    if is_json_mode():
        print_json(config)
        return
    print(f"Enabled: {on_off(config['enabled'])}")  # noqa: T201
    print(f"Country: {config['country']}")  # noqa: T201
    print(f"Domains: {domain_list(config['allowedDomains'])}")  # noqa: T201
    print(f"Countries available: {', '.join(config['availableCountries'])}")  # noqa: T201
    print(f"Price: {config['usdPerGb']} USD per GB")  # noqa: T201


@app.command(name="show")
def show() -> None:
    """Show the app's residential proxy settings."""
    settings, app_id = resolve_target()
    config = call_api(settings, "GET", _path(app_id))
    _render(config)


@app.command(name="set")
def set_config(
    enable: Annotated[
        bool | None,
        typer.Option("--enable/--disable", help="Switch the proxy on or off."),
    ] = None,
    country: Annotated[
        str | None,
        typer.Option("--country", help="Exit country code, e.g. tr (see 'show')."),
    ] = None,
    domain: Annotated[
        list[str] | None,
        typer.Option(
            "--domain",
            help="Domain to route through the proxy (repeatable): host or *.host for subdomains.",
        ),
    ] = None,
    remove_domain: Annotated[
        list[str] | None,
        typer.Option("--remove-domain", help="Domain to stop routing (repeatable)."),
    ] = None,
    clear_domains: Annotated[
        bool,
        typer.Option("--clear-domains", help="Drop every current domain before adding --domain."),
    ] = False,
) -> None:
    """Change the app's residential proxy settings; options not passed stay as they are."""
    if (
        enable is None
        and country is None
        and not domain
        and not remove_domain
        and not clear_domains
    ):
        raise fail("Nothing to change: pass --enable/--disable, --country or a domain option.")
    settings, app_id = resolve_target()
    current = call_api(settings, "GET", _path(app_id))
    if not current["available"]:
        raise fail(UNAVAILABLE_MESSAGE)

    chosen_country = country.strip().lower() if country else current["country"]
    if chosen_country not in current["availableCountries"]:
        raise fail(
            f"Unknown country '{chosen_country}'. Pick one of: "
            f"{', '.join(current['availableCountries'])}."
        )
    body = {
        "enabled": current["enabled"] if enable is None else enable,
        "country": chosen_country,
        "allowedDomains": merge_domains(
            current["allowedDomains"],
            add=domain,
            remove=remove_domain,
            clear=clear_domains,
            pattern=current["domainPattern"],
            max_domains=current["maxDomains"],
        ),
    }
    if body["enabled"] and not body["allowedDomains"]:
        print_warning("The proxy is on but no domain is listed, so no traffic goes through it.")

    updated = call_api(settings, "PUT", _path(app_id), body)
    if not is_json_mode():
        print_success("Residential proxy updated.")
    _render(updated)
