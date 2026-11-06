from enum import StrEnum
from typing import Literal, get_args

from pydantic import model_validator

from minitest_cli.models.base import CamelModel

Platform = Literal["ios", "android", "web"]
PLATFORMS: tuple[str, ...] = get_args(Platform)

_VIEWPORT_LABELS: dict[str, str] = {
    "mobile": "Mobile",
    "tablet": "Tablet",
    "pc": "Desktop",
}


class DeviceType(StrEnum):
    """Form factors the legacy ``--<platform>-device-type`` flags accept."""

    phone = "phone"
    tablet = "tablet"


TARGET_DEVICES = ("phone", "tablet", "tv")

Backend = Literal["cloud", "physical"]


class BatchTarget(CamelModel):
    platform: Platform
    build_id: str | None = None
    device_type: str | None = None
    # ``None`` lets the server default to virtual devices and keeps the
    # payload of a virtual-device run unchanged.
    backend: Backend | None = None
    device_models: list[str] | None = None
    os_version: str | None = None
    browser: str | None = None
    browser_version_requested: str | None = None
    viewport: str | None = None

    @model_validator(mode="after")
    def validate_device_type(self) -> "BatchTarget":
        if self.backend == "physical" and self.platform == "web":
            raise ValueError("Physical devices are only supported for native targets.")
        if self.device_type is None:
            return self
        if self.device_type not in TARGET_DEVICES:
            raise ValueError(f"deviceType must be one of {', '.join(TARGET_DEVICES)}.")
        if self.platform == "web" or self.backend == "physical" or self.browser is not None:
            raise ValueError("deviceType is only supported for native cloud targets.")
        if self.device_type == "tv" and self.platform != "android":
            raise ValueError("deviceType tv is only supported on Android.")
        return self


def target_label(
    platform: str,
    browser: str | None,
    viewport: str | None,
    device_type: str | None = None,
) -> str:
    if platform in {"ios", "android"}:
        if device_type == "tv":
            return "Android TV"
        label = "iOS" if platform == "ios" else "Android"
        return f"{label} · Tablet" if device_type == "tablet" else label
    if platform == "web" and browser and viewport:
        return f"{browser.title()} · {_VIEWPORT_LABELS.get(viewport.lower(), viewport)}"
    return "Web"
