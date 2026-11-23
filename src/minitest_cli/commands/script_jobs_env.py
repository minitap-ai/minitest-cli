"""The values a script job passes to its tests (`-e KEY=VALUE`, `--env-file`); never printed."""

import os
import re
from pathlib import Path

import typer

from minitest_cli.utils.output import print_error

_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _fail(message: str) -> typer.Exit:
    print_error(message)
    return typer.Exit(code=1)


def _key(key: str, where: str) -> str:
    key = key.strip()
    if not _KEY.match(key):
        raise _fail(f"{where}: '{key}' is not a valid name (letters, digits and _).")
    return key


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def read_env_file(path: Path) -> dict[str, str]:
    """KEY=VALUE lines; blank lines, `#` comments and a leading `export ` are allowed."""
    values: dict[str, str] = {}
    for number, raw in enumerate(path.read_text().splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = line.removeprefix("export ").lstrip()
        if "=" not in line:
            raise _fail(f"{path.name} line {number}: expected KEY=VALUE.")
        key, value = line.split("=", 1)
        values[_key(key, f"{path.name} line {number}")] = _unquote(value.strip())
    return values


def test_env(pairs: list[str], env_file: Path | None) -> dict[str, str]:
    """The env file first, then each `-e`: `KEY=VALUE`, or `KEY` alone to take it from the shell."""
    values = read_env_file(env_file) if env_file else {}
    for pair in pairs:
        if "=" in pair:
            key, value = pair.split("=", 1)
            values[_key(key, "-e")] = value
            continue
        key = _key(pair, "-e")
        if key not in os.environ:
            raise _fail(f"-e {key}: no {key} in the environment to pass.")
        values[key] = os.environ[key]
    return values
