"""Tell the user, once, what the last background update did."""

from minitest_cli import __version__
from minitest_cli.core.config import Settings
from minitest_cli.utils.auto_update import ENV_OPT_OUT
from minitest_cli.utils.auto_update_state import log_path, read_state, section, update_section
from minitest_cli.utils.versions import is_newer

FINISHED_STATUSES = ("done", "failed")


def pending_notices(settings: Settings) -> list[str]:
    """Return the notices not shown yet and mark them as shown."""
    state = read_state(settings)
    notices: list[str] = []

    cli = section(state, "cli")
    target = cli.get("target")
    if target and not cli.get("notified") and cli.get("status") in FINISHED_STATUSES:
        if is_newer(str(target), __version__):
            notices.append(
                f"minitest-cli could not update itself to {target} "
                f"(details: {log_path(settings)}). Run `minitest upgrade`, "
                f"or set {ENV_OPT_OUT}=1 to turn auto-update off."
            )
        else:
            notices.append(f"minitest-cli updated itself to {__version__}.")
        update_section(settings, "cli", notified=True)

    skill = section(state, "skill")
    if not skill.get("notified") and skill.get("status") in ("upgraded", "failed"):
        if skill["status"] == "upgraded":
            notices.append("The minitest-cli agent skill was refreshed to its latest version.")
        else:
            notices.append(
                "The minitest-cli agent skill could not be refreshed "
                f"(details: {log_path(settings)}). Run `minitest upgrade`."
            )
        update_section(settings, "skill", notified=True)

    return notices
