"""Lane-selection flags and target assembly for run commands."""

from typing import Annotated

import typer

from minitest_cli.models.targets import BatchTarget, DeviceType
from minitest_cli.utils.output import print_error

IosBuildOpt = Annotated[
    str | None, typer.Option("--ios-build", help="iOS build ID (selects the iOS lane).")
]
AndroidBuildOpt = Annotated[
    str | None, typer.Option("--android-build", help="Android build ID (selects the Android lane).")
]
WebOpt = Annotated[
    bool,
    typer.Option(
        "--web",
        help="Include the app's configured web targets (no build needed).",
    ),
]
IosDeviceTypeOpt = Annotated[
    DeviceType | None,
    typer.Option(
        "--ios-device-type", help="iOS cloud device type (default: phone; does not select iOS)."
    ),
]
AndroidDeviceTypeOpt = Annotated[
    DeviceType | None,
    typer.Option(
        "--android-device-type",
        help="Android cloud device type (default: phone; does not select Android).",
    ),
]


def validate_device_types(
    platforms: list[str],
    ios_device_type: DeviceType | None,
    android_device_type: DeviceType | None,
) -> None:
    for platform, device_type in (("ios", ios_device_type), ("android", android_device_type)):
        if device_type is not None and platform not in platforms:
            print_error(f"--{platform}-device-type requires the {platform} lane to be selected.")
            raise typer.Exit(code=1)


def build_targets(
    ios_build: str | None,
    android_build: str | None,
    web: bool,
    ios_device_type: DeviceType | None = None,
    android_device_type: DeviceType | None = None,
) -> list[BatchTarget]:
    targets: list[BatchTarget] = []
    if ios_build:
        targets.append(BatchTarget(platform="ios", build_id=ios_build, device_type=ios_device_type))
    if android_build:
        targets.append(
            BatchTarget(platform="android", build_id=android_build, device_type=android_device_type)
        )
    if web:
        targets.append(BatchTarget(platform="web"))
    validate_device_types(
        [target.platform for target in targets], ios_device_type, android_device_type
    )
    if not targets:
        print_error(
            "Select at least one lane: --ios-build, --android-build, or --web. "
            "Configure web targets for the app with `minitest apps`."
        )
        raise typer.Exit(code=1)
    return targets


def build_commit_targets(
    platforms: list[str] | None,
    ios_device_type: DeviceType | None,
    android_device_type: DeviceType | None,
) -> list[BatchTarget] | None:
    selected = platforms if platforms is not None else ["ios", "android"]
    validate_device_types(selected, ios_device_type, android_device_type)
    if ios_device_type is None and android_device_type is None:
        return None
    device_types = {"ios": ios_device_type, "android": android_device_type}
    return [
        BatchTarget.model_validate(
            {"platform": platform, "device_type": device_types.get(platform)}
        )
        for platform in selected
    ]
