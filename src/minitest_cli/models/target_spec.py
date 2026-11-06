"""One run target as `--target` spells it."""

from dataclasses import dataclass, fields

from minitest_cli.models.targets import BatchTarget

VIEWPORTS = {"desktop": "pc", "tablet": "tablet", "mobile": "mobile"}


@dataclass(frozen=True)
class TargetSpec:
    platform: str
    backend: str = "cloud"
    device: str | None = None
    model: str | None = None
    os: str | None = None
    browser: str | None = None
    version: str | None = None
    viewport: str | None = None
    build: str | None = None

    @property
    def native(self) -> bool:
        return self.platform != "web"

    def describe(self) -> str:
        return ",".join(
            f"{f.name}={value}" for f in fields(self) if (value := getattr(self, f.name))
        )

    def to_batch_target(self, build_id: str | None) -> BatchTarget:
        physical = self.backend == "physical"
        return BatchTarget(
            platform=self.platform,  # pyright: ignore[reportArgumentType]
            build_id=build_id,
            backend="physical" if physical else None,
            device_type=self.device if self.device != "phone" else None,
            device_models=[self.model] if self.model else None,
            os_version=self.os,
            browser=self.browser,
            browser_version_requested=self.version,
            viewport=VIEWPORTS.get(self.viewport or "", self.viewport),
        )
