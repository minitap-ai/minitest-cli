"""The `minitest run feedback` command: submit feedback on a criterion result.

The write surface for run-overview "not a bug" judgments: feedback like
"this is expected behavior, not a bug" is processed server-side and can
reclassify the result. Identity-preserving and single-field — no structural
or execution effect.
"""

from typing import Annotated

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.run_helpers import (
    ensure_uuid,
    handle_response_error,
    resolve_app,
    run_api_call,
)
from minitest_cli.utils.output import print_json, print_success


def feedback(
    result_id: Annotated[str, typer.Argument(help="Criterion result ID (from run verdicts).")],
    text: Annotated[
        str,
        typer.Argument(help="Feedback text, e.g. 'This is expected behavior, not a bug.'"),
    ],
) -> None:
    """Submit feedback on an acceptance-criterion result."""
    settings, app_id, json_mode = resolve_app()
    ensure_uuid(result_id, kind="result")

    async def _submit() -> dict:
        async with ApiClient(settings) as client:
            resp = await client.post(
                f"/api/v1/apps/{app_id}/issues/{result_id}/feedback",
                json={"feedbackText": text},
            )
            handle_response_error(resp, resource="Criterion result")
            return resp.json()

    data = run_api_call(_submit())
    if json_mode:
        print_json(data)
        return
    print_success(f"Feedback submitted on result {result_id}.")
