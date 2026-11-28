"""`minitest pr`: start a PR check, follow its event stream, and exit with its verdict."""

import json
from pathlib import Path

import httpx
import pytest

from tests.pr_backend import (
    ANDROID_BUILD,
    APP_ID,
    CHECK_ID,
    CREATE,
    EVENTS,
    FILES,
    PLAN,
    REPORT_URL,
    created,
    happy,
    invoke,
    sse,
    stream,
)


@pytest.fixture
def context(tmp_path: Path) -> Path:
    path = tmp_path / "pr.md"
    path.write_text("## Favourites\nAdd a heart on each restaurant card.\n")
    return path


def check_args(context: Path, *extra: str) -> list[str]:
    return [
        "pr", "check", "--pr", "1482", "--title", "Favourites",
        "--context-file", str(context), "--android-build", ANDROID_BUILD, *extra,
    ]  # fmt: skip


class TestStart:
    def test_check_uploads_a_build_file_and_sends_the_push(self, context: Path, tmp_path: Path):
        ipa = tmp_path / "App.ipa"
        ipa.write_bytes(b"ipa")
        commits = tmp_path / "commits.txt"
        commits.write_text("fix(cart): totals\n\nfeat(home): favourites\n")
        backend = happy()

        args = ["--ios-build", str(ipa), "--commits-file", str(commits), "--sha", "abc1234",
                "--ticket", "TIM-42"]  # fmt: skip
        result = invoke(backend, check_args(context, *args, "--full"))

        assert result.exit_code == 0, result.output
        upload = backend.sent("POST /api/v1/apps/aaaaaaaa-0000-0000-0000-000000000001/build")
        assert b'name="platform"\r\n\r\nios' in upload[0].content
        body = json.loads(backend.sent(CREATE)[0].content)
        assert body["builds"] == {
            "ios": "bbbbbbbb-0000-0000-0000-00000000000a",
            "android": ANDROID_BUILD,
        }
        assert body["commits"] == ["fix(cart): totals", "feat(home): favourites"]
        assert (body["prNumber"], body["sha"], body["full"]) == (1482, "abc1234", True)
        assert body["ticketKey"] == "TIM-42"
        assert body["context"].startswith("## Favourites")

    def test_report_link_comes_before_any_progress(self, context: Path):
        result = invoke(happy(), check_args(context))

        lines = result.stderr.splitlines()
        assert lines[0] == f"Report: {REPORT_URL}"
        assert lines.index("Plan: 2 check(s) (1 change, 1 impact)") > 0
        assert lines[-1] == f"Report: {REPORT_URL}"

    def test_without_a_report_url_the_link_is_built_from_the_app(self, context: Path):
        backend = happy().on(CREATE, httpx.Response(201, json={**created(), "reportUrl": None}))

        result = invoke(backend, check_args(context, "--no-wait"))

        assert result.exit_code == 0
        tenant = "tttttttt-0000-0000-0000-000000000001"
        assert (
            f"https://app.minitap.ai/t/{tenant}/apps/{APP_ID}/test/pr-checks/1482" in result.stderr
        )

    def test_no_build_exits_3_and_creates_nothing(self, context: Path):
        backend = happy()
        args = check_args(context)
        args.remove("--android-build")
        args.remove(ANDROID_BUILD)

        result = invoke(backend, args)

        assert result.exit_code == 3
        assert "at least one platform" in result.output
        assert backend.requests == []

    def test_context_over_the_limit_exits_3_and_sends_nothing(self, tmp_path: Path):
        long = tmp_path / "long.md"
        long.write_text("x" * 10_001)
        backend = happy()

        result = invoke(backend, check_args(long))

        assert result.exit_code == 3
        assert "10,001 characters" in result.output
        assert backend.requests == []

    def test_rejected_key_exits_3(self, context: Path):
        backend = happy().on(CREATE, httpx.Response(401, json={"detail": "Invalid API key"}))

        result = invoke(backend, check_args(context))

        assert result.exit_code == 3
        assert "Invalid API key" in result.output

    def test_usage_error_exits_3_not_2(self, context: Path):
        result = invoke(happy(), ["pr", "check", "--title", "x", "--context-file", str(context)])

        assert result.exit_code == 3

    def test_no_wait_prints_id_and_link_and_never_follows(self, context: Path):
        backend = happy()

        result = invoke(backend, check_args(context, "--no-wait"))

        assert result.exit_code == 0
        assert CHECK_ID in result.stderr and REPORT_URL in result.stderr
        assert backend.sent(EVENTS) == []


class TestWeb:
    def test_web_only_check_sends_the_url_and_uploads_nothing(self, context: Path):
        backend = happy()
        args = check_args(context, "--web-url", "https://preview.example.com/pr-1482")
        args.remove("--android-build")
        args.remove(ANDROID_BUILD)

        result = invoke(backend, [*args, "--web-browser", "firefox", "--no-wait"])

        assert result.exit_code == 0, result.output
        body = json.loads(backend.sent(CREATE)[0].content)
        assert body["web"] == {"url": "https://preview.example.com/pr-1482", "browser": "firefox"}
        assert body["builds"] == {}
        assert not [r for r in backend.requests if r.url.path.endswith("/build")]

    @pytest.mark.parametrize(
        ("extra", "says"),
        [
            (["--web-browser", "chrome"], "--web-browser needs --web-url."),
            (["--web-url", "https://x.example/" + "a" * 2000], "the limit is 2,000"),
            (["--web-browser", "safari", "--web-url", "https://x.example"], "safari"),
            (["--web-url", "preview.example.com"], "is not an http(s) URL"),
        ],
    )
    def test_invalid_web_flags_exit_3_and_send_nothing(self, context: Path, extra, says):
        backend = happy()

        result = invoke(backend, check_args(context, *extra))

        assert result.exit_code == 3
        assert says in result.output
        assert backend.requests == []

    def test_web_results_show_as_their_own_platform(self, context: Path):
        web_story = sse(
            ("pr_check.state", {"state": "exploring", "push": 1}),
            ("pr_check.plan", {"checks": PLAN, "push": 1}),
            ("pr_check.item", {"checkId": "c1", "platform": "web", "verdict": "passed", "at": 9}),
            ("pr_check.verdict", {"push": 1, "verdict": "ready", "counts": {}}),
        )

        result = invoke(happy().on(EVENTS, stream(web_story)), check_args(context))

        assert result.exit_code == 0, result.output
        assert "✓ [web]      passed     Favourite heart on each card" in result.stderr


CI_VARS = ("GITHUB_ACTIONS", "GITHUB_SERVER_URL", "GITHUB_REPOSITORY",
           "CI_MERGE_REQUEST_PROJECT_URL", "CI_MERGE_REQUEST_IID")  # fmt: skip


class TestPrUrl:
    @pytest.mark.parametrize(
        ("env", "extra", "sent"),
        [
            ({}, ["--pr-url", "https://git.example/acme/shop/pull/1482"],
             "https://git.example/acme/shop/pull/1482"),
            ({"GITHUB_ACTIONS": "true", "GITHUB_SERVER_URL": "https://github.com",
              "GITHUB_REPOSITORY": "acme/shop"}, [], "https://github.com/acme/shop/pull/1482"),
            ({"CI_MERGE_REQUEST_PROJECT_URL": "https://gitlab.com/acme/shop",
              "CI_MERGE_REQUEST_IID": "77"}, [], "https://gitlab.com/acme/shop/-/merge_requests/77"),
            ({}, [], None),
        ],
    )  # fmt: skip
    def test_pr_url_is_sent_or_derived_from_ci(self, context, monkeypatch, env, extra, sent):
        for name in CI_VARS:
            monkeypatch.delenv(name, raising=False)
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        backend = happy()

        result = invoke(backend, check_args(context, *extra, "--no-wait"))

        assert result.exit_code == 0, result.output
        assert json.loads(backend.sent(CREATE)[0].content).get("prUrl") == sent

    def test_invalid_pr_url_exits_3_and_sends_nothing(self, context: Path):
        backend = happy()

        result = invoke(backend, check_args(context, "--pr-url", "acme/shop#1482"))

        assert result.exit_code == 3
        assert "--pr-url: 'acme/shop#1482' is not an http(s) URL." in result.output
        assert backend.requests == []


class TestAttachments:
    def test_sends_supported_files_and_skips_the_rest(self, context: Path, tmp_path: Path):
        shots = tmp_path / "ctx"
        shots.mkdir()
        (shots / "mockup.png").write_bytes(b"png")
        (shots / "notes.txt").write_text("no")
        with (shots / "huge.pdf").open("wb") as f:
            f.truncate(10 * 1024 * 1024 + 1)
        (shots / "spec.pdf").write_bytes(b"pdf")
        backend = happy().on(
            FILES,
            httpx.Response(201, json={}),
            httpx.Response(415, json={"detail": "Unsupported file"}),
        )

        result = invoke(backend, check_args(context, "--attach", f"{shots}/*"))

        assert result.exit_code == 0, result.output
        sent = [r.content for r in backend.sent(FILES)]
        assert [b'filename="mockup.png"' in c for c in sent] == [True, False]
        assert b"image/png" in sent[0]
        assert json.loads(backend.sent(CREATE)[0].content)["expectedFiles"] == 2
        assert "notes.txt: only png" in result.stderr
        assert "huge.pdf: larger than 10 MB" in result.stderr
        assert "spec.pdf: rejected (415): Unsupported file" in result.stderr


class TestVerdict:
    @pytest.mark.parametrize(
        ("verdict", "extra", "code"),
        [
            ("ready", [], 0),
            ("ready_with_warnings", [], 0),
            ("ready_with_warnings", ["--fail-on", "warning"], 1),
            ("not_ready", [], 1),
            ("needs_answer", [], 2),
            ("errored", [], 3),
        ],
    )
    def test_exit_code_follows_the_verdict(self, context, verdict, extra, code):
        result = invoke(happy(verdict), check_args(context, *extra))

        assert result.exit_code == code, result.output

    def test_report_file_gets_the_server_markdown(self, context: Path, tmp_path: Path):
        out = tmp_path / "pr-check.md"

        result = invoke(happy("not_ready"), check_args(context, "--report-file", str(out)))

        assert result.exit_code == 1
        assert out.read_text() == f"## Verdict: not_ready\n\n{REPORT_URL}\n"
        assert "✗ [ios]      critical   Favourite heart on each card" in result.stderr

    def test_a_newer_push_ends_the_wait_with_3(self, context: Path):
        newer = sse(
            ("pr_check.state", {"state": "exploring", "push": 1}),
            ("pr_check.state", {"state": "preparing", "push": 2}),
        )
        backend = happy().on(EVENTS, stream(newer))

        result = invoke(backend, check_args(context))

        assert result.exit_code == 3
        assert "replaced by push 2" in result.stderr

    def test_timeout_exits_3_and_says_the_check_keeps_running(self, context: Path):
        quiet = sse(("pr_check.state", {"state": "exploring", "push": 1}))
        backend = happy().on(EVENTS, stream(quiet, hang=True))

        result = invoke(backend, check_args(context, "--timeout", "1"))

        assert result.exit_code == 3
        assert "the check keeps running" in result.stderr
        assert "minitest pr wait 1482" in result.stderr
