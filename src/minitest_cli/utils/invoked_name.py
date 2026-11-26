"""Name the CLI the way the user ran it: hints say `minitest-cli …` under `minitest-cli`."""

import re
import sys
from pathlib import Path

ALIAS = "minitest-cli"
# `minitest` followed by a subcommand or a flag, not `minitest-cli`, `minitest 6.x` or a path.
_COMMAND = re.compile(r"(?<![\w./-])minitest(?= (?:-|[a-z]))")


def invoked_name() -> str:
    return ALIAS if Path(sys.argv[0]).name.removesuffix(".exe") == ALIAS else "minitest"


def as_invoked(text: str) -> str:
    return _COMMAND.sub(ALIAS, text) if invoked_name() == ALIAS else text
