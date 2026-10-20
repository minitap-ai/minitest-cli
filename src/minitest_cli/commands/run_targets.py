"""Lane-selection flags and target assembly for run commands."""

from collections.abc import Sequence
from typing import Annotated, Literal

import typer

from minitest_cli.models.targets import BatchTarget, DeviceType
from minitest_cli.utils.output import print_error

NativePlatform = Literal["ios", "android"]

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

IosPhysicalOpt = Annotated[
    bool,
    typer.Option(
        "--ios-physical",
        help=(
            "Run the iOS lane on physical iPhones instead of simulators (needs --ios-build"
            " with a device build, and physical devices enabled for the workspace)."
        ),
    ),
]
AndroidPhysicalOpt = Annotated[
    bool,
    typer.Option(
        "--android-physical",
        help=(
            "Run the Android lane on physical phones instead of emulators (needs"
            " --android-build, and physical devices enabled for the workspace)."
        ),
    ),
]


def validate_physical(
    platforms: Sequence[str],
    physical: dict[str, bool],
    device_types: dict[str, DeviceType | None],
) -> None:
    for platform, enabled in physical.items():
        if not enabled:
            continue
        if platform not in platforms:
            print_error(f"--{platform}-physical requires --{platform}-build.")
            raise typer.Exit(code=1)
        if device_types.get(platform) is not None:
            print_error(
                f"--{platform}-physical cannot be combined with --{platform}-device-type:"
                " device types only apply to virtual devices."
            )
            raise typer.Exit(code=1)


def validate_device_types(
    platforms: Sequence[str],
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
    ios_physical: bool = False,
    android_physical: bool = False,
) -> list[BatchTarget]:
    builds: dict[NativePlatform, str | None] = {"ios": ios_build, "android": android_build}
    device_types = {"ios": ios_device_type, "android": android_device_type}
    physical = {"ios": ios_physical, "android": android_physical}
    native: list[NativePlatform] = [platform for platform, build in builds.items() if build]
    validate_physical(native, physical, device_types)
    validate_device_types(native, ios_device_type, android_device_type)
    targets = [
        BatchTarget(
            platform=platform,
            build_id=builds[platform],
            device_type=device_types[platform],
            backend="physical" if physical[platform] else None,
        )
        for platform in native
    ]
    if web:
        targets.append(BatchTarget(platform="web"))
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
