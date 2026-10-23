"""Turn the platform and source flags of `minitest schedules` into targets and sources."""

from dataclasses import dataclass
from typing import Any

from minitest_cli.commands.schedules_spec import fail
from minitest_cli.models.targets import DeviceType

BROWSERS = ("chrome", "firefox", "safari", "edge")
WEB_SURFACES = {"desktop": "pc", "mobile": "mobile", "tablet": "tablet"}
NATIVE = ("ios", "android")


@dataclass
class NativeLane:
    selected: bool = False
    build: str | None = None
    branch: str | None = None
    physical: bool = False
    device_type: DeviceType | None = None

    @property
    def given(self) -> bool:
        return bool(self.selected or self.build or self.branch or self.physical or self.device_type)


@dataclass
class WhereFlags:
    browsers: list[str] | None
    url: str | None
    web_branch: str | None
    ios: NativeLane
    android: NativeLane
    drop: list[str] | None = None

    @property
    def given(self) -> bool:
        return bool(self.browsers or self.url or self.web_branch or self.drop) or any(
            lane.given for lane in (self.ios, self.android)
        )


def parse_browser(value: str) -> dict[str, Any]:
    browser, _, surface = value.strip().lower().partition(":")
    surface = surface or "desktop"
    if browser not in BROWSERS:
        fail(f"Unknown browser {browser!r} in --browser {value!r}: use {', '.join(BROWSERS)}.")
    if surface in NATIVE:
        return {"platform": surface, "browser": browser}
    if surface not in WEB_SURFACES:
        fail(
            f"Unknown surface {surface!r} in --browser {value!r}: use desktop, mobile,"
            " tablet, android or ios."
        )
    return {"platform": "web", "browser": browser, "viewport": WEB_SURFACES[surface]}


def _is_web(target: dict[str, Any]) -> bool:
    return target.get("platform") == "web" or bool(target.get("browser"))


def _native_lane(platform: str, lane: NativeLane) -> tuple[dict[str, Any], dict[str, Any]]:
    if lane.build and lane.branch:
        fail(f"Use either --{platform}-build or --{platform}-branch, not both.")
    if lane.physical and lane.device_type:
        fail(
            f"--{platform}-physical cannot be combined with --{platform}-device-type:"
            " device types only apply to virtual devices."
        )
    target: dict[str, Any] = {"platform": platform}
    target["backend"] = "physical" if lane.physical else "cloud"
    if lane.device_type:
        target["deviceType"] = lane.device_type.value
    if lane.build:
        return target, {"mode": "fixed", "buildId": lane.build}
    if lane.branch:
        return target, {"mode": "branch", "branch": lane.branch}
    return target, {"mode": "latest"}


def resolve_where(flags: WhereFlags, current: dict[str, Any] | None) -> dict[str, Any]:
    """The schedule's targets and sources after applying the flags to ``current``."""
    current = current or {}
    targets: list[dict[str, Any]] = list(current.get("targets") or [])
    web_source = current.get("webSource")
    build_sources: dict[str, Any] = dict(current.get("buildSources") or {})

    if flags.url and flags.web_branch:
        fail("Use either --url or --web-branch, not both.")
    if flags.url or flags.web_branch:
        web_source = (
            {"mode": "url", "url": flags.url}
            if flags.url
            else {"mode": "branch", "branch": flags.web_branch}
        )
    if flags.browsers or (web_source and not any(_is_web(t) for t in targets)):
        web_targets = [parse_browser(b) for b in flags.browsers or ["chrome"]]
        targets = [t for t in targets if not _is_web(t)] + web_targets

    for platform, lane in (("ios", flags.ios), ("android", flags.android)):
        if not lane.given:
            continue
        target, source = _native_lane(platform, lane)
        targets = [t for t in targets if _is_web(t) or t.get("platform") != platform]
        targets.append(target)
        build_sources[platform] = source

    for family in flags.drop or []:
        if family == "web":
            targets, web_source = [t for t in targets if not _is_web(t)], None
        else:
            targets = [t for t in targets if _is_web(t) or t.get("platform") != family]
            build_sources.pop(family, None)

    if not targets:
        fail(
            "Select at least one platform: --url/--web-branch (with --browser), --ios or"
            " --android (with --<platform>-build or --<platform>-branch for a fixed build"
            " or a branch)."
        )
    if any(_is_web(t) for t in targets) and web_source is None:
        fail("Browser targets need a source: --url <url> or --web-branch <branch>.")
    return {
        "targets": targets,
        "webSource": web_source,
        "buildSources": build_sources or None,
    }
