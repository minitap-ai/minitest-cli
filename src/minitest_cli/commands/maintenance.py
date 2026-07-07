"""`minitest maintenance` — keep test flows in sync with local app code, no GitHub.

The customer's own coding agent runs the reasoning locally against their checkout;
only the proposed criteria edits and an opaque commit sha reach Minitest. The maintenance
"brain" is fetched from the server (composed from the same knowledge as the cloud agent),
so the CLI ships mechanics only.
"""

import sys
from typing import Annotated

import typer
from rich.console import Console
from rich.markdown import Markdown

from minitest_cli.commands.init import _is_agent_context
from minitest_cli.commands.maintenance_helpers import (
    apply_pending,
    complete_run,
    fetch_context,
    fetch_reasoning,
    open_run,
    review_queue_url,
)
from minitest_cli.commands.maintenance_state import (
    clear_handle,
    current_head_sha,
    load_handle,
    save_handle,
)
from minitest_cli.commands.maintenance_callbacks import register_callback_commands
from minitest_cli.commands.run_helpers import get_settings, is_json_mode, resolve_app, run_api_call
from minitest_cli.utils.output import (
    err_console,
    print_info,
    print_json,
    print_success,
    print_warning,
)

app = typer.Typer(
    name="maintenance",
    help="Maintain test flows against local app code (CLI-only, no GitHub).",
)
register_callback_commands(app)


@app.callback(invoke_without_command=True)
def maintenance(
    ctx: typer.Context,
    agent: bool = typer.Option(False, "--agent", help="Force raw output."),
) -> None:
    """Print the maintenance plan the customer's AI coding agent runs.

    Fetches the server-composed reasoning document (single source shared with the cloud
    maintainer) and prints it, so the local agent follows the same rules with no drift.
    """
    if ctx.invoked_subcommand is not None:
        return
    settings = get_settings()
    reasoning = run_api_call(fetch_reasoning(settings))
    if _is_agent_context(agent_flag=agent, json_mode=is_json_mode()):
        sys.stdout.write(reasoning)
        return
    err_console.print("Paste the plan below into your AI coding agent, inside your app's repo:")
    Console().print(Markdown(reasoning))


@app.command()
def context() -> None:
    """Open a maintenance run and emit its context (mode, fromSha, stories) as JSON.

    First run for an app has no watermark → audit mode (review the whole suite). Later runs
    return the previous sha so the agent diffs `git diff <fromSha>..HEAD` locally.
    """
    settings, app_id, _ = resolve_app()
    head_sha = current_head_sha()
    opened = run_api_call(open_run(settings, app_id, head_sha))
    run_id, token = opened["runId"], opened["token"]
    ctx_payload = run_api_call(fetch_context(settings, run_id, token))
    save_handle({"runId": run_id, "token": token, "appId": app_id, "headSha": head_sha})
    guardrail = opened.get("guardrail", {})
    if guardrail.get("hasPending"):
        print_warning(
            f"{guardrail.get('pendingCount')} change(s) still awaiting review. "
            "Tidy the release queue before maintaining so in-flight edits aren't clobbered."
        )
    print_json(
        {
            "runId": run_id,
            "mode": opened.get("mode"),
            "fromSha": opened.get("fromSha"),
            "headSha": head_sha,
            "guardrail": guardrail,
            "context": ctx_payload,
        }
    )


@app.command()
def complete(
    changed: Annotated[
        bool,
        typer.Option("--changed/--no-changed", help="Whether ≥1 change was proposed."),
    ],
) -> None:
    """Close the run. Advances the watermark only when a genuine change was produced."""
    handle = load_handle()
    run_api_call(complete_run(get_settings(), handle["runId"], changed=changed))
    clear_handle()
    print_success("Maintenance run complete.")


@app.command()
def apply(
    review: Annotated[
        bool,
        typer.Option("--review", help="Print the Release Queue link instead of applying now."),
    ] = False,
) -> None:
    """Apply pending maintenance edits now, or print the Release Queue link."""
    settings, app_id, _ = resolve_app()
    if review:
        print_info(f"Review maintenance changes: {review_queue_url(settings, app_id)}")
        return
    result = run_api_call(apply_pending(settings, app_id))
    print_success(f"Applied {result.get('appliedCount', 0)} maintenance change(s).")
    print_info(f"Review remaining changes: {result.get('reviewUrl')}")
