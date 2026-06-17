"""Request-side execution-target model and label helper.

A run selects *lanes* (ios / android / web). Native lanes carry the build
under test; the bare ``{"platform": "web"}`` marker tells the server to expand
the app's configured default web targets. Per-run web overrides (url, browser,
viewport) are CI-only and intentionally absent from the CLI.
"""

from typing import Literal

from minitest_cli.models.base import CamelModel

_VIEWPORT_LABELS: dict[str, str] = {
    "mobile": "Mobile",
    "tablet": "Tablet",
    "pc": "Desktop",
}


class BatchTarget(CamelModel):
    """One execution lane in a CreateBatchRequest.

    Native lanes are ``{platform, build_id}``; the web lane is the bare
    ``{platform: "web"}`` marker the server expands into the app's default
    web targets.
    """

    platform: Literal["ios", "android", "web"]
    build_id: str | None = None


def target_label(platform: str, browser: str | None, viewport: str | None) -> str:
    """Render a human label for a target, matching testing-service's scheme."""
    if platform == "ios":
        return "iOS"
    if platform == "android":
        return "Android"
    if platform == "web" and browser and viewport:
        return f"{browser.title()} · {_VIEWPORT_LABELS.get(viewport.lower(), viewport)}"
    return "Web"
