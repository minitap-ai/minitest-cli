"""Detect another program answering to `minitest` on PATH (Ruby's test runner, minitest 6+)."""

import os
import shutil
import subprocess
from dataclasses import dataclass

from minitest_cli.utils.output import print_warning

VERSION_PREFIX = "minitest-cli "


@dataclass(frozen=True)
class PathClash:
    path: str
    version_output: str


def find_path_clash() -> PathClash | None:
    resolved = shutil.which("minitest")
    if resolved is None:
        return None
    try:
        result = subprocess.run(
            [resolved, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            stdin=subprocess.DEVNULL,
            check=False,
        )
        output = (result.stdout.strip() or result.stderr.strip()).splitlines()
    except (OSError, subprocess.TimeoutExpired):
        output = []
    first_line = output[0] if output else ""
    if first_line.startswith(VERSION_PREFIX):
        return None
    return PathClash(path=resolved, version_output=first_line)


def warn_if_shadowed() -> None:
    clash = find_path_clash()
    if clash is None:
        return
    own_script = shutil.which("minitest-cli")
    path_fix = (
        f"put {os.path.dirname(own_script)} first in PATH"
        if own_script
        else "put the folder of minitest-cli first in PATH"
    )
    printed = f" (it prints {clash.version_output!r})" if clash.version_output else ""
    print_warning(
        f"`minitest` on your PATH is {clash.path}{printed}, not this CLI: "
        "Ruby's minitest gem installs a `minitest` command that does nothing with "
        f"minitest-cli commands and still exits 0. Run `minitest-cli` instead, or {path_fix}."
    )
