"""Rows of the `apps list` table."""

from minitest_cli.models.app import AppResponse

APP_TABLE_HEADERS = ["ID", "Name", "Platform", "Repository", "Folder"]

_PLATFORM_LABELS: dict[str, str] = {
    "android": "Android",
    "ios": "iOS",
    "web": "Web",
}


def _format_platforms(values: list[str]) -> str:
    if not values:
        return "—"
    return ", ".join(_PLATFORM_LABELS.get(v, v) for v in values)


def app_row(app: AppResponse) -> list[str]:
    repo = app.repository
    return [
        app.id,
        app.name,
        _format_platforms(app.platforms),
        repo.full_name if repo else "—",
        (repo.folder or "/") if repo else "—",
    ]
