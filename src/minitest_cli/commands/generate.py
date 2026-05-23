"""Generation-job commands: start, status, list."""

from typing import Annotated, Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.generate_helpers import (
    JOB_TABLE_HEADERS,
    base_path,
    format_job_row,
    get_app_flag,
    get_settings,
    handle_response_error,
    is_json_mode,
    run_api_call,
)
from minitest_cli.core.app_context import resolve_app_id
from minitest_cli.core.auth import require_auth
from minitest_cli.utils.output import output, print_info, print_success, print_table

app = typer.Typer(name="generate", help="AI-powered user story generation from your codebase.")


@app.command(name="start")
def start_generation(
    repo_owner: Annotated[str, typer.Option("--repo-owner", help="GitHub repository owner.")],
    repo_name: Annotated[str, typer.Option("--repo-name", help="GitHub repository name.")],
    repo_ref: Annotated[
        str, typer.Option("--ref", help="Git ref (branch, tag, or commit).")
    ] = "main",
) -> None:
    """Start AI generation of user stories from a GitHub repository."""
    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)
    app_id = resolve_app_id(settings, get_app_flag())

    payload: dict[str, str] = {
        "repoOwner": repo_owner,
        "repoName": repo_name,
        "repoRef": repo_ref,
    }

    async def _run() -> dict[str, Any]:
        async with ApiClient(settings) as client:
            resp = await client.post(base_path(app_id), json=payload)
            handle_response_error(resp)
            return resp.json()

    data = run_api_call(_run())
    if json_mode:
        output(data, json_mode=True)
    else:
        print_success(f"Generation job started: {data.get('id', '')}")
        print_info(f"Status: {data.get('status', '')}")
        print_info(f"Track progress: minitest generate status {data.get('id', '')}")


@app.command(name="status")
def get_generation_status(
    job_id: Annotated[str, typer.Argument(help="Generation job ID.")],
) -> None:
    """Show details and status updates for a generation job."""
    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)
    app_id = resolve_app_id(settings, get_app_flag())

    async def _run() -> dict[str, Any]:
        async with ApiClient(settings) as client:
            resp = await client.get(f"{base_path(app_id)}/{job_id}")
            handle_response_error(resp)
            return resp.json()

    data = run_api_call(_run())
    if json_mode:
        output(data, json_mode=True)
        return

    print_info(f"Job {data.get('id', '')}")
    print_info(f"  Status: {data.get('status', '')}")
    repo = f"{data.get('repoOwner', '')}/{data.get('repoName', '')}"
    print_info(f"  Repo: {repo} (ref: {data.get('repoRef', '')})")
    print_info(f"  Stories created: {data.get('userStoriesCreated', 0)}")

    updates = data.get("statusUpdates", [])
    if updates:
        print_info("")
        rows = [
            [u.get("category", ""), u.get("message", ""), str(u.get("createdAt", ""))[:16]]
            for u in updates
        ]
        print_table(["Phase", "Message", "Time"], rows, title="Status updates")


@app.command(name="list")
def list_generation_jobs(
    page: Annotated[int, typer.Option("--page", min=1, help="Page number.")] = 1,
    page_size: Annotated[
        int, typer.Option("--page-size", min=1, max=100, help="Items per page.")
    ] = 20,
) -> None:
    """List generation jobs for the active app."""
    settings = get_settings()
    json_mode = is_json_mode()
    require_auth(settings)
    app_id = resolve_app_id(settings, get_app_flag())

    params: dict[str, int] = {"page": page, "page_size": page_size}

    async def _run() -> dict[str, Any]:
        async with ApiClient(settings) as client:
            resp = await client.get(base_path(app_id), params=params)
            handle_response_error(resp)
            return resp.json()

    data = run_api_call(_run())
    if json_mode:
        output(data, json_mode=True)
        return

    raw_items = data if isinstance(data, list) else data.get("items", [])
    items: list[dict[str, Any]] = [i for i in raw_items if isinstance(i, dict)]
    if not items:
        print_info("No generation jobs found.")
        return

    rows = [format_job_row(j) for j in items]
    print_table(JOB_TABLE_HEADERS, rows, title="Generation jobs")
