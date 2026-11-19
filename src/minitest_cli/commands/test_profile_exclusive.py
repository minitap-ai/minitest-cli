"""``--exclusive/--no-exclusive``: one run at a time on a test account."""

from typing import Annotated

import typer

ExclusiveOption = Annotated[
    bool | None,
    typer.Option(
        "--exclusive/--no-exclusive",
        help="One run at a time on this account: runs that use it wait for each other. "
        "For accounts whose data parallel runs would collide on (an open order, a cart).",
    ),
]
