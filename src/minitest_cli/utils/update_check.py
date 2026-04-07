"""PyPI version check – cached for 24 hours, non-blocking, max 2s timeout."""

import json
import shutil
import sys
import time
from pathlib import Path

import httpx

from minitest_cli import __version__
from minitest_cli.core.config import Settings
from minitest_cli.utils.output import print_warning

CACHE_FILE_NAME = ".last_update_check"
CACHE_TTL_SECONDS = 86400  # 24 hours
CHECK_TIMEOUT_SECONDS = 2.0
PYPI_URL = "https://pypi.org/pypi/minitest-cli/json"


def _cache_path(settings: Settings) -> Path:
    return settings.ensure_config_dir() / CACHE_FILE_NAME


def _read_cache(settings: Settings) -> dict | None:
    """Read the cached version check result, if still valid."""
    path = _cache_path(settings)
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text())
        if time.time() - data.get("checked_at", 0) < CACHE_TTL_SECONDS:
            return data
    except (json.JSONDecodeError, OSError):
        pass

    return None


def _write_cache(settings: Settings, latest_version: str) -> None:
    """Write the latest version to the cache file."""
    path = _cache_path(settings)
    try:
        path.write_text(json.dumps({"latest_version": latest_version, "checked_at": time.time()}))
    except OSError:
        pass


def _is_brew_install() -> bool:
    """Detect if the running minitest binary was installed via Homebrew."""
    exe = shutil.which("minitest")
    if exe is None:
        exe = sys.executable
    return "/Cellar/" in exe or "/homebrew/" in exe.lower()


def _version_tuple(v: str) -> tuple[int, ...]:
    """Parse a version string like '0.4.3' into a comparable tuple (0, 4, 3)."""
    try:
        return tuple(int(x) for x in v.split("."))
    except (ValueError, AttributeError):
        return (0,)


def _is_newer(latest: str, current: str) -> bool:
    """Return True if latest is strictly newer than current."""
    return _version_tuple(latest) > _version_tuple(current)


def _upgrade_command() -> str:
    """Return the appropriate upgrade command based on install method."""
    if _is_brew_install():
        return "brew upgrade minitest-cli"
    return "pip install --upgrade minitest-cli"


def check_for_updates(settings: Settings) -> None:
    """Check PyPI for a newer version and warn on stderr if available.

    This function never raises exceptions or blocks the CLI for more than 2 seconds.
    """
    try:
        cached = _read_cache(settings)
        if cached:
            latest = cached.get("latest_version", __version__)
        else:
            response = httpx.get(PYPI_URL, timeout=CHECK_TIMEOUT_SECONDS)
            response.raise_for_status()
            latest = response.json()["info"]["version"]
            _write_cache(settings, latest)

        if _is_newer(latest, __version__):
            upgrade_cmd = _upgrade_command()
            print_warning(
                f"A new version of minitest-cli is available: {latest} "
                f"(current: {__version__}). "
                f"Update with: {upgrade_cmd}"
            )
    except Exception:  # noqa: BLE001
        # Never block or crash the CLI for an update check failure
        pass
