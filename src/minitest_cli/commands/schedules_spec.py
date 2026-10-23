"""Parse the When / Summary flags of `minitest schedules create|update` into API fields."""

import os
import re
from pathlib import Path
from typing import Any, NoReturn
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import typer
import yaml

from minitest_cli.utils.output import print_error

DAY_NAMES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DAY_PRESETS = {
    "weekdays": [0, 1, 2, 3, 4],
    "weekends": [5, 6],
    "every-day": [0, 1, 2, 3, 4, 5, 6],
    "daily": [0, 1, 2, 3, 4, 5, 6],
}
_TIME = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)(:00)?$")
# Fields the API returns but never accepts back, so `get --json` output loads as a file.
RESPONSE_ONLY = {
    "id",
    "appId",
    "tenantId",
    "createdBy",
    "createdAt",
    "updatedAt",
    "deletedAt",
    "nextRunAt",
    "scenarioCount",
    "etaSeconds",
}


def fail(message: str) -> NoReturn:
    print_error(message)
    raise typer.Exit(code=1)


def parse_time(value: str) -> str:
    match = _TIME.match(value.strip())
    if match is None:
        fail(f"Invalid time {value!r}: use 24-hour HH:MM, e.g. 03:00.")
    return f"{int(match.group(1)):02d}:{match.group(2)}"


def parse_days(value: str) -> list[int]:
    text = value.strip().lower()
    if text in DAY_PRESETS:
        return DAY_PRESETS[text]
    days: set[int] = set()
    for part in filter(None, (p.strip() for p in text.split(","))):
        if part[:3] in DAY_NAMES:
            days.add(DAY_NAMES.index(part[:3]))
        elif part.isdigit() and int(part) < 7:
            days.add(int(part))
        else:
            fail(
                f"Invalid --days {value!r}: use weekdays, weekends, every-day, or a list"
                " like mon,wed,fri (or 0-6, 0=Monday)."
            )
    if not days:
        fail("--days needs at least one day.")
    return sorted(days)


def check_timezone(name: str) -> str:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        fail(f"Unknown timezone {name!r}: use an IANA name like Europe/Oslo or America/New_York.")
    return name


def local_timezone() -> str:
    """The system's IANA zone, from $TZ or /etc/localtime; UTC when neither names one."""
    candidates = [os.environ.get("TZ", "").lstrip(":")]
    localtime = Path("/etc/localtime")
    if localtime.is_symlink():
        candidates.append(str(localtime.resolve()).partition("zoneinfo/")[2])
    for name in candidates:
        try:
            if name:
                ZoneInfo(name)
                return name
        except (ZoneInfoNotFoundError, ValueError):
            continue
    return "UTC"


def load_file(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        fail(f"Cannot read {path}: {exc.strerror}.")
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        fail(f"{path} is not valid JSON or YAML: {exc}")
    if not isinstance(data, dict):
        fail(f"{path} must hold one schedule object (the shape `schedules get --json` prints).")
    body = {key: value for key, value in data.items() if key not in RESPONSE_ONLY}
    time_of_day = body.get("timeOfDay")
    # YAML 1.1 reads an unquoted 03:00 as the sexagesimal integer 180.
    if isinstance(time_of_day, int):
        time_of_day = f"{time_of_day // 60:02d}:{time_of_day % 60:02d}"
    if time_of_day is not None:
        body["timeOfDay"] = parse_time(str(time_of_day))
    if "timezone" in body:
        check_timezone(str(body["timezone"]))
    return body
