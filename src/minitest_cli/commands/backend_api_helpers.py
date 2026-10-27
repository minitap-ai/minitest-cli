"""Rendering and secret-list editing for 'apps backend-api'."""

from typing import Any

from minitest_cli.commands.app_network_helpers import fail, is_json_mode, on_off
from minitest_cli.utils.output import print_json, print_warning


def merge_secret_names(
    current: list[str], *, add: list[str] | None, remove: list[str] | None, clear: bool
) -> list[str]:
    """Apply ``--clear-secrets``, ``--remove-secret`` then ``--secret``."""
    removed = {name.strip() for name in remove or []}
    unknown = sorted(removed - set(current))
    if unknown:
        raise fail(f"Not an authentication secret of this app: {', '.join(unknown)}.")
    base = [] if clear else [name for name in current if name not in removed]
    return list(dict.fromkeys([*base, *(name.strip() for name in add or [])]))


def render_config(config: dict[str, Any]) -> None:
    if is_json_mode():
        print_json(config)
    else:
        skill = config["skill"]
        print(f"Enabled: {on_off(config['enabled'])}")  # noqa: T201
        print(f"Base URL: {config['baseUrl'] or '-'}")  # noqa: T201
        print(f"OpenAPI URL: {config['openapiUrl'] or '-'}")  # noqa: T201
        secrets = ", ".join(config["authenticationSecretNames"]) or "-"
        print(f"Authentication secrets: {secrets}")  # noqa: T201
        print(f"Skill: {skill['name'] + ' ' + skill['id'] if skill else '-'}")  # noqa: T201
    missing = config["missingSecretNames"]
    if missing:
        print_warning(
            f"Not in the app vault anymore: {', '.join(missing)}. Create them with "
            "'minitest secret set' or drop them with --remove-secret."
        )
