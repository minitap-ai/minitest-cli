"""Rendering and connector lookup for 'apps private-network'."""

from typing import Any

from minitest_cli.commands.app_network_helpers import domain_list, fail, is_json_mode, on_off
from minitest_cli.utils.output import print_info, print_json, print_table, print_warning

UNAVAILABLE_MESSAGE = "This workspace cannot use private network. Contact Minitap to enable it."
CREATE_IN_WEBAPP_HINT = (
    "Connectors can only be created by a workspace owner or admin in the webapp: "
    "Workspace settings → Private network."
)


def resolve_connector(connectors: list[dict[str, Any]], ref: str) -> dict[str, Any]:
    """Find a connector by id, or by name (case-insensitive)."""
    if not connectors:
        raise fail(f"This workspace has no connector. {CREATE_IN_WEBAPP_HINT}")
    by_id = [c for c in connectors if c["id"] == ref]
    matches = by_id or [c for c in connectors if c["name"].casefold() == ref.casefold()]
    if len(matches) == 1:
        return matches[0]
    if matches:
        ids = ", ".join(c["id"] for c in matches)
        raise fail(f"Several connectors are named '{ref}': pass one of these ids instead: {ids}.")
    names = ", ".join(f"{c['name']} ({c['status']})" for c in connectors)
    raise fail(f"No connector named '{ref}'. Available: {names}. {CREATE_IN_WEBAPP_HINT}")


def without_token_prefix(config: dict[str, Any]) -> dict[str, Any]:
    connector = config.get("connector")
    if not connector:
        return config
    return {**config, "connector": {k: v for k, v in connector.items() if k != "tokenPrefix"}}


def render_config(config: dict[str, Any]) -> None:
    config = without_token_prefix(config)
    if not config["available"]:
        print_warning(UNAVAILABLE_MESSAGE)
    if is_json_mode():
        print_json(config)
        warn_connector_state(config)
        return
    connector = config["connector"]
    print(f"Enabled: {on_off(config['enabled'])}")  # noqa: T201
    if connector:
        print(f"Connector: {connector['name']} ({connector['status']}) {connector['id']}")  # noqa: T201
    else:
        print("Connector: -")  # noqa: T201
    print(f"Domains: {domain_list(config['domains'])}")  # noqa: T201
    print(f"Ports: {', '.join(str(p) for p in config['ports']) or '-'}")  # noqa: T201
    warn_connector_state(config)


def warn_connector_state(config: dict[str, Any]) -> None:
    connector = config["connector"]
    if config["enabled"] and connector and connector["status"] != "online":
        print_warning(
            f"Connector '{connector['name']}' is {connector['status']}: runs cannot reach "
            "the internal domains until it is connected."
        )
    refused = config["domainsRefusedByConnector"]
    if refused:
        print_warning(
            f"The connector's own allowlist refuses: {', '.join(refused)}. Add them on the "
            "connector machine, or the devices will not reach them."
        )


def render_connectors(listing: dict[str, Any]) -> None:
    if not listing["available"]:
        print_warning(UNAVAILABLE_MESSAGE)
    connectors = listing["connectors"]
    if not connectors:
        print_info(f"No connector yet. {CREATE_IN_WEBAPP_HINT}")
    if is_json_mode():
        print_json(listing)
        return
    if not connectors:
        return
    rows = [
        [
            c["name"],
            c["status"],
            domain_list(c["domains"]),
            ", ".join(str(p) for p in c["ports"]) or "-",
            c.get("lastSeenAt") or "-",
            c["id"],
        ]
        for c in connectors
    ]
    print_table(["Name", "Status", "Domains", "Ports", "Last seen", "ID"], rows, title="Connectors")
