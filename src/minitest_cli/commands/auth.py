"""Authentication commands: login, logout, status."""

import json
import subprocess
from datetime import UTC, datetime

import typer

from minitest_cli.core.auth import (
    AuthStatus,
    clear_credentials,
    decode_jwt_claims,
    get_auth_method,
    load_or_refresh_credentials,
    oauth_pkce_login,
)
from minitest_cli.core.config import Settings
from minitest_cli.utils.output import output, print_error, print_info, print_success

app = typer.Typer(name="auth", help="Authentication management.")

SKILL_NAME = "minitest-cli"
SKILL_INSTALL_CMD = "npx skills add minitap-ai/agent-skills --skill minitest-cli"


def _is_skill_installed() -> bool:
    """Check if the minitest-cli skill is installed via ``npx skills ls``.

    Queries both project-level and global scopes so the detection stays in
    sync with whatever directories the ``skills`` CLI manages.
    """
    for flags in (["--json"], ["--json", "-g"]):
        try:
            result = subprocess.run(
                ["npx", "skills", "ls", *flags],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                skills = json.loads(result.stdout)
                if any(s.get("name") == SKILL_NAME for s in skills):
                    return True
        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError, OSError):
            # npx not available or unexpected output – fall through
            pass
    return False


def _get_settings() -> Settings:
    """Retrieve settings stored by the main callback."""
    return typer.Context.settings  # type: ignore[attr-defined]


def _is_json_mode() -> bool:
    """Retrieve the global --json flag."""
    return typer.Context.json_mode  # type: ignore[attr-defined]


@app.command()
def login() -> None:
    """Authenticate with the Minitest platform via OAuth PKCE."""
    settings = _get_settings()

    if settings.token:
        print_error("MINITEST_TOKEN environment variable is set. Unset it to use OAuth login.")
        raise typer.Exit(code=2)

    creds = oauth_pkce_login(settings)
    print_success(f"Authenticated as {creds.email}")

    # Check if the minitest-cli agent skill is installed
    if not _is_skill_installed():
        print_info("")
        print_info("💡 The minitest-cli agent skill is not installed in this project.")
        print_info("   Your AI agent needs it to know how to use minitest.")
        print_info("")
        try:
            answer = input("   Install it now? [Y/n] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "n"
            print()  # newline after ^C / ^D
        if answer in ("", "y", "yes"):
            print_info("")
            print_info(f"   Running: {SKILL_INSTALL_CMD}")
            print_info("")
            subprocess.run(SKILL_INSTALL_CMD.split(), check=False)
        else:
            print_info("")
            print_info("   You can install it later with:")
            print_info(f"   {SKILL_INSTALL_CMD}")
            print_info("")


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
    """Show current authentication status."""
    settings = _get_settings()
    json_mode = _is_json_mode()
    method = get_auth_method(settings)

    if method == "env_token":
        claims = decode_jwt_claims(settings.token) if settings.token else {}
        try:
            expires_at_iso = datetime.fromtimestamp(int(claims["exp"]), tz=UTC).isoformat()
        except (KeyError, ValueError, TypeError, OverflowError, OSError):
            expires_at_iso = None
        data: AuthStatus = {
            "token_configured": True,
            "method": "env_token",
            "user_id": claims.get("sub"),
            "email": claims.get("email"),
            "expires_at": expires_at_iso,
        }
        output(data, json_mode=json_mode)
        return

    if method == "oauth":
        # get_auth_method already validated/refreshed credentials, so this is safe
        creds = load_or_refresh_credentials(settings)
        assert creds is not None  # guaranteed by get_auth_method returning "oauth"
        expires_at_iso = datetime.fromtimestamp(creds.expires_at, tz=UTC).isoformat()
        data: AuthStatus = {
            "token_configured": True,
            "method": "oauth",
            "user_id": creds.user_id,
            "email": creds.email,
            "expires_at": expires_at_iso,
        }
        output(data, json_mode=json_mode)
        return

    # Not authenticated
    data: AuthStatus = {
        "token_configured": False,
        "method": "none",
        "user_id": None,
        "email": None,
        "expires_at": None,
    }
    if json_mode:
        output(data, json_mode=True)
    else:
        print_error("Not authenticated. Run `minitest auth login` or set MINITEST_TOKEN.")
    raise typer.Exit(code=2)
