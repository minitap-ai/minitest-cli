"""`--target` on `minitest schedules`: the platforms it names get exactly those targets."""

from typing import Any

from minitest_cli.commands.schedules_spec import fail
from minitest_cli.models.target_spec import VIEWPORTS, TargetSpec


def schedule_target(spec: TargetSpec) -> dict[str, Any]:
    if spec.build:
        fail(
            f"--target {spec.describe()}: a schedule takes its builds from --{spec.platform}-build,"
            f" --{spec.platform}-branch or the latest build; drop build=."
        )
    if spec.version:
        fail(f"--target {spec.describe()}: schedules do not take a browser version yet.")
    if not spec.native:
        target: dict[str, Any] = {"platform": "web", "browser": spec.browser or "chrome"}
        target["viewport"] = VIEWPORTS[spec.viewport or "desktop"]
        return target
    target = {"platform": spec.platform, "backend": spec.backend}
    if spec.device and spec.device != "phone":
        target["deviceType"] = spec.device
    if spec.model:
        target["deviceModel"] = spec.model
    if spec.os:
        target["osVersion"] = spec.os
    return target


def _is_web(target: dict[str, Any]) -> bool:
    return target.get("platform") == "web" or bool(target.get("browser"))


def apply_specs(
    specs: list[TargetSpec],
    targets: list[dict[str, Any]],
    build_sources: dict[str, Any],
    lanes_given: dict[str, bool],
) -> list[dict[str, Any]]:
    """``targets`` with every platform the specs name replaced by their targets."""
    if not specs:
        return targets
    native = {spec.platform for spec in specs if spec.native}
    web = any(not spec.native for spec in specs)
    kept = [
        t
        for t in targets
        if not (_is_web(t) and web) and not (not _is_web(t) and t.get("platform") in native)
    ]
    for platform in native:
        if lanes_given.get(platform):
            fail(
                f"--{platform}-physical / --{platform}-device-type cannot be combined with"
                f" --target platform={platform}: put backend= or device= in the target."
            )
        build_sources.setdefault(platform, {"mode": "latest"})
    return kept + [schedule_target(spec) for spec in specs]
