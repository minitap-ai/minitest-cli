"""Keep `minitest draft show|apply|delete` working for scripts written before `draft` meant Mini.

From v0.34 to v0.36 `draft` named the low-level branch commands now under `minitest df`.
The names that do not clash with the new group stay as hidden aliases that warn on stderr.
"""

import functools
from collections.abc import Callable
from typing import Any

import typer
from typer.models import CommandInfo

from minitest_cli.commands import draft_feature
from minitest_cli.utils.output import print_warning

LEGACY_NAMES = ("show", "apply", "delete")


def _warning(name: str, callback: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(callback)
    def _legacy(*args: Any, **kwargs: Any) -> Any:
        print_warning(f"`minitest draft {name}` is deprecated; use `minitest df {name}` instead.")
        return callback(*args, **kwargs)

    return _legacy


def register(app: typer.Typer) -> None:
    for info in draft_feature.app.registered_commands:
        if info.name not in LEGACY_NAMES or info.callback is None:
            continue
        app.registered_commands.append(
            CommandInfo(
                name=info.name,
                callback=_warning(info.name, info.callback),
                hidden=True,
                help=f"Deprecated: use `minitest df {info.name}`.",
            )
        )
