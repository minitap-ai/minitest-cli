"""The `minitest run verdicts` command: product-level batch verdicts."""

from typing import Annotated

import typer

from minitest_cli.commands.run_helpers import ensure_uuid, resolve_app, run_api_call
from minitest_cli.commands.verdicts_helpers import VALID_PLATFORMS, fetch_verdicts
from minitest_cli.utils.output import print_error, print_json


def verdicts(
    batch_id: Annotated[str, typer.Argument(help="Batch ID to summarise verdicts for.")],
    platform: Annotated[
        str | None, typer.Option(help="Filter to one platform (ios/android/web).")
    ] = None,
    only_failed: Annotated[
        bool, typer.Option("--only-failed", help="Drop fully-passing stories.")
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", help="Include passing criteria and per-criterion evidence."),
    ] = False,
) -> None:
    """Product-level pass/fail verdicts for a batch, projected as JSON."""
    settings, app_id, _ = resolve_app()
    ensure_uuid(batch_id, kind="batch")
    if platform is not None and platform not in VALID_PLATFORMS:
        print_error(
            f"Unknown platform '{platform}'. Expected one of: {', '.join(VALID_PLATFORMS)}."
        )
        raise typer.Exit(1)
    result = run_api_call(
        fetch_verdicts(
            settings,
            app_id,
            batch_id,
            platform=platform,
            only_failed=only_failed,
            verbose=verbose,
        )
    )
    print_json(result)
