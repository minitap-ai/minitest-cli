"""`--target key=value,...` and `--targets-file`: the run targets a command asks for.

The same key=value spec is read by the minitest-trigger GitHub Action's ``targets:`` input.
"""

import json
from pathlib import Path
from typing import Annotated

import typer

from minitest_cli.commands.target_rules import TargetSpecError, check_spec
from minitest_cli.models.target_spec import TargetSpec
from minitest_cli.utils.output import print_error

SPEC_KEYS = (
    "platform",
    "backend",
    "device",
    "model",
    "os",
    "browser",
    "version",
    "viewport",
    "build",
)
_LOWERCASE_KEYS = {"platform", "backend", "device", "browser", "viewport"}

TargetOpt = Annotated[
    list[str] | None,
    typer.Option(
        "--target",
        help=(
            "A target as key=value pairs, repeatable: platform (ios|android|web, required),"
            " backend (cloud|physical), device (phone|tablet|tv), model, os, browser"
            " (chrome|edge|firefox), version (browser major), viewport (desktop|tablet|mobile),"
            ' build. E.g. platform=ios,os=27 or "platform=ios,backend=physical,model=iPhone 13".'
        ),
    ),
]
TargetsFileOpt = Annotated[
    Path | None,
    typer.Option(
        "--targets-file",
        help="JSON list of targets, each an object with the --target keys.",
        exists=True,
        dir_okay=False,
    ),
]


def parse_target(raw: str) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for part in raw.split(","):
        key, sep, value = part.partition("=")
        key = key.strip().lower()
        if not sep or not key:
            raise TargetSpecError(f"{part.strip()!r} is not key=value")
        if key in pairs:
            raise TargetSpecError(f"{key} is given twice")
        pairs[key] = value.strip()
    return pairs


def to_spec(raw: dict[str, object]) -> TargetSpec:
    unknown = sorted(set(raw) - set(SPEC_KEYS))
    if unknown:
        raise TargetSpecError(f"unknown key {unknown[0]!r}: use {', '.join(SPEC_KEYS)}")
    values = {
        key: (str(value).strip().lower() if key in _LOWERCASE_KEYS else str(value).strip())
        for key, value in raw.items()
        if value is not None and str(value).strip()
    }
    if "platform" not in values:
        raise TargetSpecError("platform is required (ios, android or web)")
    return check_spec(TargetSpec(**values))


def _load_file(path: Path) -> list[dict[str, object]]:
    try:
        entries = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise TargetSpecError(f"cannot read it as JSON ({exc})") from exc
    if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
        raise TargetSpecError("it must be a JSON list of objects")
    return entries


def collect_specs(targets: list[str] | None, targets_file: Path | None) -> list[TargetSpec]:
    specs: list[TargetSpec] = []
    source = ""
    try:
        for raw in targets or []:
            source = f"--target {raw!r}"
            specs.append(to_spec(dict(parse_target(raw))))
        if targets_file is not None:
            source = f"--targets-file {targets_file}"
            for index, entry in enumerate(_load_file(targets_file), start=1):
                source = f"--targets-file {targets_file}, entry {index}"
                specs.append(to_spec(entry))
    except TargetSpecError as exc:
        print_error(f"Invalid {source}: {exc}.")
        raise typer.Exit(code=1) from exc
    return specs
