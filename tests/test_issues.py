"""Behavior tests for ``minitest issues list``."""

import asyncio
import json
from contextlib import contextmanager
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from typer.testing import CliRunner

from minitest_cli.commands.issues_projection import build_block
from minitest_cli.commands.issues_service import collect_issues
from minitest_cli.core.config import Settings
from minitest_cli.main import app as cli
from minitest_cli.models.batch import BatchResponse

APP_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
BATCH_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
LATEST_BATCH_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
RUN_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"
ISSUE_ID = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"


def _batch(batch_id: str, *, context: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "id": batch_id,
        "appId": APP_ID,
        "tenantId": "tenant",
        "source": "api",
        "status": "completed",
        "commitSha": None,
        "createdAt": datetime.now(UTC).isoformat(),
        "targets": [
            {
                "id": "target",
                "platform": "web",
                "label": "Web",
                "buildContext": context,
            }
        ],
    }


FAILURE = {
    "id": ISSUE_ID,
    "status": "open",
    "criticality": "warning",
    "platform": "web",
    "storyRunId": RUN_ID,
    "batchId": BATCH_ID,
    "rcaPrompt": "Apply the targeted fix.",
    "webappIssueUrl": f"https://dev.minitap.ai/issues?issueId={ISSUE_ID}",
}


@contextmanager
def _api_server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            path, _, query = self.path.partition("?")
            params = dict(part.split("=", 1) for part in query.split("&") if "=" in part)
            failures_path = f"/api/v1/apps/{APP_ID}/failures"
            batches_path = f"/api/v1/apps/{APP_ID}/batches"
            if path == f"{batches_path}/latest":
                payload = _batch(LATEST_BATCH_ID, context={"commitSha": "abcdef123456"})
            elif path == batches_path:
                payload = {
                    "items": [_batch(LATEST_BATCH_ID), _batch(BATCH_ID)],
                    "total": 2,
                    "page": 1,
                    "pageSize": 100,
                }
            elif path in {f"{batches_path}/{BATCH_ID}", f"{batches_path}/{LATEST_BATCH_ID}"}:
                payload = _batch(path.rsplit("/", 1)[-1])
            elif path == f"/api/v1/apps/{APP_ID}/story-runs/{RUN_ID}":
                payload = {"batchId": BATCH_ID}
            elif path == f"{failures_path}/{ISSUE_ID}":
                payload = FAILURE
            elif path == f"{failures_path}/count":
                payload = {"count": 1 if params.get("batch_id") == BATCH_ID else 0}
            elif path == failures_path:
                scoped = params.get("batch_id") == BATCH_ID or params.get("story_run_id") == RUN_ID
                payload = {
                    "items": [FAILURE] if scoped else [],
                    "total": 1 if scoped else 0,
                    "page": 1,
                    "pageSize": 100,
                }
            else:
                self.send_error(404)
                return
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()


def _collect(api_url: str, **scope: str | None):
    return asyncio.run(
        collect_issues(
            Settings(api_url=api_url, token="token"),
            APP_ID,
            issue_id=scope.get("issue_id"),
            story_run_id=scope.get("story_run_id"),
            batch_id=scope.get("batch_id"),
            platform=None,
            criticality=None,
            include_resolved=False,
        )
    )


class TestIssueScopes:
    def test_list_defaults_to_latest_batch_and_advertises_other_open_issues(self):
        with _api_server() as api_url:
            result = _collect(api_url)

        assert result.scope.kind == "latest_batch"
        assert result.scope.batch_id == LATEST_BATCH_ID
        assert result.scope.other_batches_with_open_issues == 1
        assert result.scope.open_issues_in_other_batches == 1
        assert result.issues == []

    def test_list_supports_each_explicit_scope(self):
        with _api_server() as api_url:
            batch = _collect(api_url, batch_id=BATCH_ID)
            run = _collect(api_url, story_run_id=RUN_ID)
            issue = _collect(api_url, issue_id=ISSUE_ID)

        assert (batch.scope.kind, batch.scope.batch_id) == ("batch", BATCH_ID)
        assert (run.scope.kind, run.scope.story_run_id) == ("run", RUN_ID)
        assert (issue.scope.kind, issue.scope.issue_id) == ("issue", ISSUE_ID)
        assert all(
            result.issues[0].fix_prompt == "Apply the targeted fix."
            for result in (batch, run, issue)
        )
        assert all(
            result.issues[0].deeplink == f"https://dev.minitap.ai/issues?issueId={ISSUE_ID}"
            for result in (batch, run, issue)
        )

    def test_list_rejects_multiple_scopes(self):
        result = CliRunner().invoke(cli, ["issues", "list", "--issue", ISSUE_ID, "--run", RUN_ID])

        assert result.exit_code == 1
        assert "Choose only one scope" in result.stderr


class TestBuildProjection:
    def test_build_uses_exact_provenance_tiers(self):
        commit = BatchResponse.model_validate(
            _batch(BATCH_ID, context={"commitSha": "1234567890abcdef"})
        )
        version = BatchResponse.model_validate(
            _batch(BATCH_ID, context={"appVersion": "2.4.0", "buildNumber": "91"})
        )

        assert build_block(commit).summary == "observed on commit 1234567"
        assert build_block(version).summary == "observed on version 2.4.0 (build 91)"
        assert build_block(None).summary == "no build info attached"

    def test_build_withholds_infra_fix_prompt_but_surfaces_code_fix_prompt(self):
        infra = BatchResponse.model_validate(
            _batch(
                BATCH_ID,
                context={"status": "failed", "errorClass": "infra", "errorFixPrompt": "secret"},
            )
        )
        code = BatchResponse.model_validate(
            _batch(
                BATCH_ID,
                context={"status": "failed", "errorClass": "code", "errorFixPrompt": "fix it"},
            )
        )

        assert infra.targets[0].build_context is not None
        assert build_block(infra).failures[0].fix_prompt is None
        assert build_block(infra).failures[0].fix_prompt_withheld is True
        assert build_block(code).failures[0].fix_prompt == "fix it"
        assert build_block(code).failures[0].fix_prompt_withheld is False
