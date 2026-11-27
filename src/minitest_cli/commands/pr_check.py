"""`minitest pr check`: send a PR's builds and text to Mini and wait for its verdict."""

import json
from pathlib import Path
from typing import Annotated, Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.draft_helpers import DraftTarget, run_conductor
from minitest_cli.commands.pr_api import (
    PR_CHECKS_PATH,
    conductor,
    errors_exit_3,
    pr_target,
    report_url,
    request,
)
from minitest_cli.commands.pr_inputs import (
    WebBrowser,
    check_build_values,
    check_web,
    pr_url,
    expand_attachments,
    read_commits,
    read_context,
    resolve_builds,
    send_attachments,
)
from minitest_cli.commands.pr_outcome import FailOn, FailOnOpt, ReportFileOpt, TimeoutOpt
from minitest_cli.commands.pr_render import console
from minitest_cli.commands.pr_wait import WaitOptions, follow_push

BUILD_HELP = "A build file to upload (.ipa, .app.zip, .apk, .apks, .aab) or an uploaded build id."


def register(app: typer.Typer) -> None:
    @app.command(name="check")
    def check(
        pr: Annotated[int, typer.Option("--pr", min=1, help="Pull request number.")],
        title: Annotated[str, typer.Option("--title", help="Pull request title.")],
        context_file: Annotated[
            str,
            typer.Option(
                "--context-file",
                help="Markdown: the PR description and its ticket (≤10,000 chars); - is stdin.",
            ),
        ],
        pr_url_flag: Annotated[
            str | None,
            typer.Option(
                "--pr-url",
                help="The PR's page, linked from the report (default on GitHub Actions/GitLab CI).",
            ),
        ] = None,
        ios_build: Annotated[str | None, typer.Option("--ios-build", help=BUILD_HELP)] = None,
        android_build: Annotated[
            str | None, typer.Option("--android-build", help=BUILD_HELP)
        ] = None,
        web_url: Annotated[
            str | None, typer.Option("--web-url", help="URL of the web app build to check.")
        ] = None,
        web_browser: Annotated[
            WebBrowser | None,
            typer.Option("--web-browser", help="Browser for --web-url (default: Chrome)."),
        ] = None,
        commits_file: Annotated[
            str | None,
            typer.Option("--commits-file", help="The push's commit messages, one per line."),
        ] = None,
        ticket: Annotated[
            str | None, typer.Option("--ticket", help="Ticket key the PR implements, e.g. TIM-123.")
        ] = None,
        sha: Annotated[
            str | None, typer.Option("--sha", help="Head commit SHA of the push.")
        ] = None,
        attach: Annotated[
            list[str] | None,
            typer.Option(
                "--attach",
                help="Glob of images/PDFs for Mini (png, jpg, gif, webp, pdf; ≤10 MB). Repeatable.",
            ),
        ] = None,
        full: Annotated[
            bool,
            typer.Option("--full", help="Re-run every check, not only what this push changes."),
        ] = False,
        fail_on: FailOnOpt = FailOn.CRITICAL,
        report_file: ReportFileOpt = None,
        no_wait: Annotated[
            bool, typer.Option("--no-wait", help="Start the check, print its link and exit 0.")
        ] = False,
        timeout: TimeoutOpt = None,
    ) -> None:
        """Check a PR on its builds or web app: exit 0 ready, 1 not ready, 2 question, 3 error."""
        context = read_context(context_file)
        commits = read_commits(commits_file)
        link = pr_url(pr_url_flag, pr)
        web = check_web(web_url, web_browser)
        builds = check_build_values(
            {"ios": ios_build, "android": android_build}, web=web is not None
        )
        files = expand_attachments(attach or [])
        target = pr_target()
        body: dict[str, object] = {
            "tenantId": target.tenant_id,
            "appId": target.app_id,
            "prNumber": pr,
            "title": title,
            "context": context,
            "full": full,
        }
        if link is not None:
            body["prUrl"] = link
        if web is not None:
            body["web"] = web
        if commits is not None:
            body["commits"] = commits
        if sha:
            body["sha"] = sha
        if ticket:
            body["ticketKey"] = ticket
        if files:
            body["expectedFiles"] = len(files)
        options = WaitOptions(fail_on, report_file, timeout)
        with errors_exit_3():
            code = run_conductor(_run(target, builds, body, files, options, no_wait=no_wait))
        raise typer.Exit(code=code)


async def _run(
    target: DraftTarget,
    builds: dict[str, str],
    body: dict[str, object],
    files: list[Path],
    options: WaitOptions,
    *,
    no_wait: bool,
) -> int:
    async with ApiClient(target.settings) as testing_service:
        body["builds"] = await resolve_builds(testing_service, target.app_id, builds)
    async with conductor(target) as client:
        created = await request(
            client, target, "POST", PR_CHECKS_PATH, what="Starting the PR check", json=body
        )
        url = report_url(target, created.get("reportUrl"), created["prNumber"])
        _announce_start(created, url, json_mode=target.json_mode)
        await send_attachments(client, target, created["id"], files)
        if no_wait:
            return 0
        return await follow_push(client, target, created, url, options)


def _announce_start(created: dict[str, Any], url: str, *, json_mode: bool) -> None:
    if json_mode:
        line = {"type": "pr_check.created", "data": {**created, "reportUrl": url}}
        print(json.dumps(line), flush=True)  # noqa: T201
        return
    console.print(f"Report: {url}")
    console.print(
        f"PR check {created['id']} · PR #{created['prNumber']} · push {created['push']}"
        f" · {created['state']}"
    )
