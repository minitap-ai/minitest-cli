"""The target rules testing-service applies, checked before anything is sent."""

import re
from collections.abc import Iterable
from dataclasses import replace

import typer

from minitest_cli.models.target_spec import VIEWPORTS, TargetSpec
from minitest_cli.models.targets import PLATFORMS, TARGET_DEVICES, BatchTarget
from minitest_cli.utils.output import print_error

BROWSERS = ("chrome", "edge", "firefox")
_VERSION = re.compile(r"^\d+(\.\d+)*$")


class TargetSpecError(ValueError):
    pass


def _choice(key: str, value: str | None, choices: Iterable[str]) -> None:
    options = tuple(choices)
    if value is not None and value not in options:
        raise TargetSpecError(f"{key}={value} is not one of {', '.join(options)}")


def _forbid(spec: TargetSpec, keys: Iterable[str], reason: str) -> None:
    for key in keys:
        if getattr(spec, key) is not None:
            raise TargetSpecError(f"{key} {reason}")


def _check_web(spec: TargetSpec) -> TargetSpec:
    if spec.backend == "physical":
        raise TargetSpecError("backend=physical needs a native platform (ios or android)")
    if spec.device is not None:
        raise TargetSpecError("device does not apply to web targets: use viewport=")
    _forbid(spec, ("model", "os", "build"), "does not apply to web targets")
    if spec.version is not None:
        if spec.browser is None:
            raise TargetSpecError("version needs browser=")
        if spec.viewport == "mobile":
            raise TargetSpecError("version is not available on viewport=mobile")
        if not spec.version.isdigit():
            raise TargetSpecError(f"version={spec.version} must be a browser major, e.g. 157")
    return spec


def _cloud_os(os: str) -> str:
    """The catalog lists majors (26, 27), so 27.0 means 27."""
    major, _, rest = os.partition(".")
    return major if rest.strip("0.") == "" else os


def _check_native(spec: TargetSpec) -> TargetSpec:
    _forbid(spec, ("browser", "version", "viewport"), "only applies to platform=web")
    if spec.device == "tv" and spec.platform != "android":
        raise TargetSpecError("device=tv needs platform=android")
    if spec.backend == "physical":
        if spec.device is not None:
            raise TargetSpecError("device only applies to cloud devices: use model= instead")
        if spec.os is not None and spec.model is None:
            raise TargetSpecError("os on a physical target needs model=")
    elif spec.model is not None:
        raise TargetSpecError("model needs backend=physical: pick cloud devices with device=")
    if spec.os is None:
        return spec
    if spec.device == "tv":
        raise TargetSpecError("os does not apply to device=tv")
    if not _VERSION.match(spec.os):
        raise TargetSpecError(f"os={spec.os} must be a version number, e.g. 27")
    return spec if spec.backend == "physical" else replace(spec, os=_cloud_os(spec.os))


def check_spec(spec: TargetSpec) -> TargetSpec:
    _choice("platform", spec.platform, PLATFORMS)
    _choice("backend", spec.backend, ("cloud", "physical"))
    _choice("device", spec.device, TARGET_DEVICES)
    _choice("browser", spec.browser, BROWSERS)
    _choice("viewport", spec.viewport, VIEWPORTS)
    return _check_native(spec) if spec.native else _check_web(spec)


def target_key(target: BatchTarget) -> tuple[object, ...]:
    """Mirrors testing-service's target key: two targets with one key are one target."""
    native_cloud = target.platform != "web" and target.backend != "physical" and not target.browser
    models = target.device_models or []
    return (
        target.platform,
        target.backend or "cloud",
        (target.device_type or "phone") if native_cloud else target.device_type,
        models[0] if len(models) == 1 else None,
        target.os_version,
        target.browser,
        target.browser_version_requested,
        target.viewport,
    )


def check_lanes(targets: list[BatchTarget]) -> None:
    seen: set[tuple[object, ...]] = set()
    builds: dict[tuple[str, bool], str] = {}
    for target in targets:
        key = target_key(target)
        if key in seen:
            print_error(
                f"The same {target.platform} target is listed twice: each device or browser"
                " may appear once per run."
            )
            raise typer.Exit(code=1)
        seen.add(key)
        if target.build_id is None:
            continue
        slot = (target.platform, target.backend == "physical")
        if builds.setdefault(slot, target.build_id) != target.build_id:
            kind = "physical" if slot[1] else "cloud"
            print_error(
                f"{target.platform} {kind} targets install different builds: every {kind}"
                f" {target.platform} target of a run installs the same build."
            )
            raise typer.Exit(code=1)
