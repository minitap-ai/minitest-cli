"""Authentication commands: login, logout, status."""

from datetime import UTC, datetime
from typing import Annotated

import typer

from minitest_cli.commands.auth_api_key import app as api_key_app
from minitest_cli.core.auth import (
    AuthStatus,
    clear_credentials,
    decode_jwt_claims,
    get_auth_method,
    load_or_refresh_credentials,
    oauth_pkce_login,
)
from minitest_cli.core.config import Settings
from minitest_cli.core.oauth import DEFAULT_LOGIN_TIMEOUT_SECONDS
from minitest_cli.utils import skill_bundle
from minitest_cli.utils.skill_refresh import find_conventional_skill_path
from minitest_cli.utils.output import output, print_error, print_info, print_success

app = typer.Typer(name="auth", help="Authentication management.")
app.add_typer(api_key_app, name="api-key")


def _get_settings() -> Settings:
    """Retrieve settings stored by the main callback."""
    return typer.Context.settings  # type: ignore[attr-defined]


def _is_json_mode() -> bool:
    """Retrieve the global --json flag."""
    return typer.Context.json_mode  # type: ignore[attr-defined]


@app.command()
def login(
    no_browser: Annotated[
        bool,
        typer.Option("--no-browser", help="Print the sign-in URL instead of opening a browser."),
    ] = False,
    timeout: Annotated[
        int,
        typer.Option(
            "--timeout",
            min=1,
            help=f"Seconds to wait for the sign-in (default {DEFAULT_LOGIN_TIMEOUT_SECONDS}).",
        ),
    ] = DEFAULT_LOGIN_TIMEOUT_SECONDS,
) -> None:
    """Authenticate with the Minitest platform via OAuth PKCE.

    With --json, the sign-in URL is printed on stdout as a JSON line
    ({"authorize_url": ...}) before waiting, then the result as a second JSON line.
    """
    settings = _get_settings()
    json_mode = _is_json_mode()

    if settings.token:
        print_error("MINITEST_TOKEN environment variable is set. Unset it to use OAuth login.")
        raise typer.Exit(code=2)

    creds = oauth_pkce_login(
        settings, open_browser=not no_browser, timeout=timeout, json_mode=json_mode
    )
    if json_mode:
        output(
            {"authenticated": True, "email": creds.email, "user_id": creds.user_id}, json_mode=True
        )
        return
    print_success(f"Authenticated as {creds.email}")
    if find_conventional_skill_path() is None:
        print_info(
            "Tip: `minitest skill` prints the agent skill for this CLI version; install it with "
            f"`{' '.join(skill_bundle.install_command())}`."
        )


@app.command()
def logout() -> None:
    """Remove stored credentials."""
    settings = _get_settings()

    if settings.token:
        print_error(
            "Using MINITEST_TOKEN environment variable. Unset it to manage OAuth credentials."
        )
        raise typer.Exit(code=2)

    clear_credentials(settings)
    print_success("Logged out. Credentials removed.")


@app.command()
def status() -> None:
    """Show current authentication status.

    expires_at is when the current access token expires. An OAuth login with
    refreshable=true renews that token by itself, so it lasts until logout.
    """
    settings = _get_settings()
    json_mode = _is_json_mode()
    method = get_auth_method(settings)

    if method == "env_token":
        claims = decode_jwt_claims(settings.token) if settings.token else {}
        try:
            expires_at_iso = datetime.fromtimestamp(int(claims["exp"]), tz=UTC).isoformat()
        except (KeyError, ValueError, TypeError, OverflowError, OSError):
            expires_at_iso = None
        _print_status(
            {
                "token_configured": True,
                "method": "env_token",
                "user_id": claims.get("sub"),
                "email": claims.get("email"),
                "expires_at": expires_at_iso,
                "refreshable": False,
            },
            json_mode=json_mode,
        )
        return

    if method == "api_key":
        _print_status(
            {
                "token_configured": True,
                "method": "api_key",
                "user_id": None,
                "email": None,
                "expires_at": None,
                "refreshable": False,
            },
            json_mode=json_mode,
        )
        return

    if method == "oauth":
        # get_auth_method already validated/refreshed credentials, so this is safe
        creds = load_or_refresh_credentials(settings)
        assert creds is not None  # guaranteed by get_auth_method returning "oauth"
        _print_status(
            {
                "token_configured": True,
                "method": "oauth",
                "user_id": creds.user_id,
                "email": creds.email,
                "expires_at": datetime.fromtimestamp(creds.expires_at, tz=UTC).isoformat(),
                "refreshable": bool(creds.refresh_token),
            },
            json_mode=json_mode,
        )
        return

    data: AuthStatus = {
        "token_configured": False,
        "method": "none",
        "user_id": None,
        "email": None,
        "expires_at": None,
        "refreshable": False,
    }
    if json_mode:
        output(data, json_mode=True)
    else:
        print_error("Not authenticated. Run `minitest auth login` or set MINITEST_TOKEN.")
    raise typer.Exit(code=2)


def _print_status(data: AuthStatus, *, json_mode: bool) -> None:
    if json_mode:
        output(data, json_mode=True)
        return
    human = {k: v for k, v in data.items() if k not in ("expires_at", "refreshable")}
    if data["expires_at"]:
        human["access_token_expires_at"] = data["expires_at"]
    output(human, json_mode=False)
    if data["refreshable"]:
        print_info("This login renews itself: the CLI refreshes the access token as needed.")
