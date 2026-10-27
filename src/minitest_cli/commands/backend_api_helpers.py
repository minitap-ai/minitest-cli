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


OPENAPI_AUTH_TYPES = ("none", "bearer", "header", "basic", "query")
_AUTH_NAME_FIELD = {
    "header": ("headerName", "--openapi-auth-header"),
    "basic": ("username", "--openapi-auth-username"),
    "query": ("paramName", "--openapi-auth-param"),
}


def openapi_auth_body(
    current: dict[str, Any],
    *,
    auth_type: str | None,
    secret: str | None,
    names: dict[str, str | None],
) -> dict[str, Any]:
    """Apply the --openapi-auth options to the saved setting; ``names`` is keyed by option."""
    kind = auth_type or current["type"]
    if kind not in OPENAPI_AUTH_TYPES:
        raise fail(f"--openapi-auth must be one of: {', '.join(OPENAPI_AUTH_TYPES)}.")
    field = _AUTH_NAME_FIELD.get(kind)
    stray = [
        option for option, value in names.items() if value and (not field or option != field[1])
    ]
    if kind == "none" and secret:
        stray.insert(0, "--openapi-auth-secret")
    if stray:
        raise fail(f"{', '.join(stray)} does not apply to --openapi-auth {kind}.")
    if kind == "none":
        return {"type": "none"}
    same = current["type"] == kind
    body = {"type": kind, "secretName": secret or (current.get("secretName") if same else None)}
    if field:
        body[field[0]] = names[field[1]] or (current.get(field[0]) if same else None)
    required = [("--openapi-auth-secret", body["secretName"])] + (
        [(field[1], body[field[0]])] if field else []
    )
    missing = [option for option, value in required if not value]
    if missing:
        raise fail(f"--openapi-auth {kind} needs {' and '.join(missing)}.")
    return body


def _describe_openapi_auth(auth: dict[str, Any]) -> str:
    if auth["type"] == "none":
        return "none"
    field = _AUTH_NAME_FIELD.get(auth["type"])
    detail = f" {field[0]}={auth[field[0]]}" if field else ""
    return f"{auth['type']}{detail} secret={auth['secretName']}"


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
        print(f"OpenAPI download: {_describe_openapi_auth(config['openapiAuth'])}")  # noqa: T201
    missing = config["missingSecretNames"]
    if missing:
        print_warning(
            f"Not in the app vault anymore: {', '.join(missing)}. Create them with "
            "'minitest secret set' or drop them with --remove-secret."
        )
    if config["openapiAuthSecretMissing"]:
        print_warning(
            f"The OpenAPI download secret {config['openapiAuth']['secretName']} is not in the "
            "app vault anymore: runs will not start until it is created again or replaced."
        )
