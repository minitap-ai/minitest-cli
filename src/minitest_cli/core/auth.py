"""Token management: read/write tokens from config dir and environment."""

import json
import sys
from pathlib import Path

from minitest_cli.core.config import Settings

EXIT_CODE_AUTH_ERROR = 2
TOKEN_FILE_NAME = "credentials.json"


def get_token_path(settings: Settings) -> Path:
    """Return the path to the credentials file."""
    return settings.ensure_config_dir() / TOKEN_FILE_NAME


def load_token(settings: Settings) -> str:
    """Load the auth token.

    Priority:
      1. MINITEST_TOKEN environment variable (via settings.token)
      2. ~/.minitest/credentials.json file

    Returns:
        The bearer token string.
    """
    if settings.token:
        return settings.token

    token_path = get_token_path(settings)
    if token_path.exists():
        data = json.loads(token_path.read_text())
        token = data.get("token")
        if isinstance(token, str) and token:
            return token

    print(  # noqa: T201
        "Error: Not authenticated. Run `minitest auth login` or set MINITEST_TOKEN.",
        file=sys.stderr,
    )
    raise SystemExit(EXIT_CODE_AUTH_ERROR)


def save_token(settings: Settings, token: str) -> None:
    """Persist the token to ~/.minitest/credentials.json."""
    token_path = get_token_path(settings)
    token_path.write_text(json.dumps({"token": token}))
    token_path.chmod(0o600)


def clear_token(settings: Settings) -> None:
    """Remove the persisted token."""
    token_path = get_token_path(settings)
    if token_path.exists():
        token_path.unlink()
