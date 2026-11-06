"""Targets of `minitest run from-commit`: built from the commit unless they pin a build."""

from collections.abc import Sequence

import typer

from minitest_cli.commands.run_targets import reject_legacy_overlap, validate_device_types
from minitest_cli.commands.target_rules import check_lanes
from minitest_cli.models.target_spec import TargetSpec
from minitest_cli.models.targets import BatchTarget, DeviceType
from minitest_cli.utils.output import print_error


def build_commit_targets(
    platforms: list[str] | None,
    ios_device_type: DeviceType | None,
    android_device_type: DeviceType | None,
    specs: Sequence[TargetSpec] = (),
) -> tuple[list[BatchTarget] | None, list[str] | None]:
    """The targets and the platforms the commit builds, as the batch request carries them."""
    if not specs:
        selected = platforms if platforms is not None else ["ios", "android"]
        validate_device_types(selected, ios_device_type, android_device_type)
        if ios_device_type is None and android_device_type is None:
            return None, platforms
        device_types = {"ios": ios_device_type, "android": android_device_type}
        legacy = [
            BatchTarget.model_validate(
                {"platform": platform, "device_type": device_types.get(platform)}
            )
            for platform in selected
        ]
        return legacy, None
    device_types = {"ios": ios_device_type, "android": android_device_type}
    reject_legacy_overlap(specs, device_types)
    built = [spec.platform for spec in specs if not (spec.native and spec.build)]
    scope = platforms or list(dict.fromkeys(built))
    if not scope:
        print_error("A commit run needs at least one target built from the commit (no build=).")
        raise typer.Exit(code=1)
    for spec in specs:
        if spec.native and spec.build and spec.platform in scope:
            print_error(
                f"--target {spec.describe()} pins a build, but {spec.platform} is built from the"
                f" commit: drop build= or leave {spec.platform} out of --platform."
            )
            raise typer.Exit(code=1)
        if spec.platform not in scope and not spec.build:
            print_error(f"--target platform={spec.platform} is not in --platform {scope}.")
            raise typer.Exit(code=1)
    validate_device_types(scope, ios_device_type, android_device_type)
    named = {spec.platform for spec in specs}
    targets = [
        BatchTarget.model_validate({"platform": p, "device_type": device_types[p]})
        for p in ("ios", "android")
        if p in scope and p not in named and device_types[p]
    ]
    targets += [spec.to_batch_target(spec.build) for spec in specs]
    check_lanes(targets)
    return targets, scope
