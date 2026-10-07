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
    phone = "phone"
    tablet = "tablet"


class BatchTarget(CamelModel):
    platform: Platform
    build_id: str | None = None
    device_type: DeviceType | None = None

    @model_validator(mode="before")
    @classmethod
    def validate_cloud_device_type(cls, data: object) -> object:
        if isinstance(data, dict) and data.get("deviceType", data.get("device_type")) is not None:
            if data.get("backend", "cloud") != "cloud" or any(
                data.get(field) is not None for field in ("browser", "url", "viewport")
            ):
                raise ValueError("deviceType is only supported for native cloud targets.")
        return data

    @model_validator(mode="after")
    def validate_device_type(self) -> "BatchTarget":
        if self.device_type is not None and self.platform == "web":
            raise ValueError("deviceType is only supported for native cloud targets.")
        return self


def target_label(
    platform: str,
    browser: str | None,
    viewport: str | None,
    device_type: str | None = None,
) -> str:
    if platform in {"ios", "android"}:
        label = "iOS" if platform == "ios" else "Android"
        return f"{label} · Tablet" if device_type == "tablet" else label
    if platform == "web" and browser and viewport:
        return f"{browser.title()} · {_VIEWPORT_LABELS.get(viewport.lower(), viewport)}"
    return "Web"
