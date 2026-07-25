"""Credentials model and secure file I/O."""

from __future__ import annotations

import fcntl
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel

from minitest_cli.core.config import Settings

if TYPE_CHECKING:
    from collections.abc import Iterator

TOKEN_FILE_NAME = "credentials.json"
LOCK_FILE_NAME = "credentials.lock"
CREDENTIALS_FILE_MODE = 0o600  # owner read/write only
REFRESH_BUFFER_SECONDS = 300  # refresh when < 5 minutes remain


class Credentials(BaseModel):
    """Persisted OAuth credentials."""

    access_token: str
    refresh_token: str
    expires_at: float
    user_id: str
    email: str
    client_id: str | None = None

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
    """Persist credentials atomically with restricted permissions."""
    path = get_credentials_path(settings)
    tmp_path = path.with_name(f".{path.name}.tmp")
    fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, CREDENTIALS_FILE_MODE)
    with os.fdopen(fd, "w") as handle:
        handle.write(credentials.model_dump_json(indent=2))
    os.replace(tmp_path, path)


@contextmanager
def refresh_lock(settings: Settings) -> Iterator[None]:
    """Serialise token refresh across processes sharing this config dir."""
    lock_path = settings.ensure_config_dir() / LOCK_FILE_NAME
    fd = os.open(lock_path, os.O_WRONLY | os.O_CREAT, CREDENTIALS_FILE_MODE)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def clear_credentials(settings: Settings) -> None:
    """Remove the persisted credentials file."""
    path = get_credentials_path(settings)
    if path.exists():
        path.unlink()
