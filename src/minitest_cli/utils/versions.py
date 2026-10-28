"""Compare minitest-cli version strings."""


def version_tuple(version: str) -> tuple[int, ...]:
    """Parse a version string like '0.4.3' into a comparable tuple (0, 4, 3)."""
    try:
        return tuple(int(part) for part in version.split("."))
    except (ValueError, AttributeError):
        return (0,)


def is_newer(latest: str, current: str) -> bool:
    """Return True if latest is strictly newer than current."""
    return version_tuple(latest) > version_tuple(current)
