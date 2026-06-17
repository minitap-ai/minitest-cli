"""Lane-selection flags and target assembly for run commands."""

from typing import Annotated

import typer

from minitest_cli.models.targets import BatchTarget
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


def build_targets(ios_build: str | None, android_build: str | None, web: bool) -> list[BatchTarget]:
    """Map the lane flags to execution targets; require at least one lane."""
    targets: list[BatchTarget] = []
    if ios_build:
        targets.append(BatchTarget(platform="ios", build_id=ios_build))
    if android_build:
        targets.append(BatchTarget(platform="android", build_id=android_build))
    if web:
        targets.append(BatchTarget(platform="web"))
    if not targets:
        print_error(
            "Select at least one lane: --ios-build, --android-build, or --web. "
            "Configure web targets for the app with `minitest apps`."
        )
        raise typer.Exit(code=1)
    return targets
