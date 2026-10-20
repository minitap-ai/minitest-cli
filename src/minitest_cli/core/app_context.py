"""App targeting: resolve the active app ID from --app flag or MINITEST_APP_ID.

Both accept an app id or an app name; a name is looked up once in the apps the
caller can see (the same lookup `draft` and `env` use), an id is used as is.
"""

import asyncio
import sys
import threading
from uuid import UUID

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
    target = app_flag or settings.app_id
    if not target:
        print(  # noqa: T201
            "Error: No app specified. Use --app <id-or-name> or set MINITEST_APP_ID.",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_CODE_GENERAL_ERROR)
    if _is_uuid(target):
        return target
    return _app_id_by_name(settings, target)


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
    except ValueError:
        return False
    return True


def _app_id_by_name(settings: Settings, name: str) -> str:
    """Look the name up; exits 4 when no app has it, 1 when several do."""
    from minitest_cli.commands.env_helpers import resolve_app_and_tenant

    result: list[str] = []
    failure: list[BaseException] = []

    def lookup() -> None:
        try:
            app_id, _ = asyncio.run(resolve_app_and_tenant(settings, name))
            result.append(app_id)
        except BaseException as exc:  # noqa: BLE001 - re-raised on the caller's thread
            failure.append(exc)

    # A thread of its own, so this works whether or not the caller runs an event loop.
    worker = threading.Thread(target=lookup)
    worker.start()
    worker.join()
    if failure:
        raise failure[0]
    return result[0]
