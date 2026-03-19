"""App targeting: resolve the active app ID from --app flag or MINITEST_APP_ID."""

import sys

from minitest_cli.core.config import Settings

EXIT_CODE_GENERAL_ERROR = 1


def resolve_app_id(settings: Settings, app_flag: str | None = None) -> str:
    """Resolve the target app ID.

    Priority:
      1. --app flag value (passed explicitly)
      2. MINITEST_APP_ID environment variable (via settings)
      3. Exit with error if neither is set

    Returns:
        The resolved app ID string.
    """
    if app_flag:
        return app_flag

    if settings.app_id:
        return settings.app_id

    print(  # noqa: T201
        "Error: No app specified. Use --app <id-or-name> or set MINITEST_APP_ID.",
        file=sys.stderr,
    )
    raise SystemExit(EXIT_CODE_GENERAL_ERROR)
