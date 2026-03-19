"""Credentials model and secure file I/O."""

from __future__ import annotations

import json
import time
from pathlib import Path

from pydantic import BaseModel

from minitest_cli.core.config import Settings

TOKEN_FILE_NAME = "credentials.json"
CREDENTIALS_FILE_MODE = 0o600  # owner read/write only
REFRESH_BUFFER_SECONDS = 300  # refresh when < 5 minutes remain


class Credentials(BaseModel):
    """Persisted OAuth credentials."""

    access_token: str
    refresh_token: str
    expires_at: float
    user_id: str
    email: str

    @property
    def is_expired(self) -> bool:
        """Return True if the token has expired or will within the refresh buffer."""
        return time.time() >= (self.expires_at - REFRESH_BUFFER_SECONDS)


def get_credentials_path(settings: Settings) -> Path:
    """Return the path to the credentials file."""
    return settings.ensure_config_dir() / TOKEN_FILE_NAME


def load_credentials(settings: Settings) -> Credentials | None:
    """Load credentials from disk, or None if missing/invalid."""
    path = get_credentials_path(settings)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        return Credentials.model_validate(data)
    except (json.JSONDecodeError, ValueError):
        return None


def save_credentials(settings: Settings, credentials: Credentials) -> None:
    """Persist credentials to disk with restricted permissions."""
    path = get_credentials_path(settings)
    path.write_text(credentials.model_dump_json(indent=2))
    path.chmod(CREDENTIALS_FILE_MODE)


def clear_credentials(settings: Settings) -> None:
    """Remove the persisted credentials file."""
    path = get_credentials_path(settings)
    if path.exists():
        path.unlink()
