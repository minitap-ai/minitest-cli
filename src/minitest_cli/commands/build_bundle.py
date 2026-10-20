"""Human rendering of an uploaded build, including the members of an .aab bundle group."""

from typing import Any

import typer

from minitest_cli.commands.build_conversion import variant_label
from minitest_cli.models import BuildResponse
from minitest_cli.utils.output import output, print_table

BUNDLE_TABLE_HEADERS = ["ID", "Device", "Status", "ABIs", "Error"]
_BACKEND_LABELS = {"cloud": "cloud emulators", "physical": "physical phones"}

PHYSICAL_AAB_NOTE = (
    "--physical is not needed for .aab uploads: the bundle converts for both"
    " cloud and physical devices."
)


def _human_fields(build: BuildResponse) -> dict[str, Any]:
    """The build's fields for ``key: value`` lines: lists joined, members shown apart."""
    fields = build.model_dump(mode="json", by_alias=True, exclude={"variants"})
    for key, value in fields.items():
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            fields[key] = ", ".join(value) or "-"
    return fields


def runs_on(backends: list[str]) -> str:
    labels = [_BACKEND_LABELS.get(backend, backend) for backend in backends]
    return " and ".join(labels) if labels else "no device (no build of this upload completed)"


def print_uploaded_build(build: BuildResponse) -> None:
    """Print the build, then each bundle member and the devices it can run on."""
    output(_human_fields(build), json_mode=False)
    if build.variants:
        rows = [
            [
                v.id,
                variant_label(v),
                v.status or "-",
                ", ".join(v.abis or []) or "-",
                (v.error_summary or "-") if v.status == "failed" else "",
            ]
            for v in build.variants
        ]
        title = f"This .aab converted into {len(rows)} builds"
        print_table(BUNDLE_TABLE_HEADERS, rows, title=title)
    if build.supported_backends is not None:
        typer.echo(f"Runs on: {runs_on(build.supported_backends)}")
    if sum(v.status == "completed" for v in build.variants or []) > 1:
        typer.echo(
            f"Start runs with --android-build {build.id}: Minitap picks the right build"
            " for emulators and for physical phones (--android-physical)."
        )
