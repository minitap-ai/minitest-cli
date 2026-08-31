"""Failed builds must yield labelled guidance, and never leak internals (PRD US-5)."""

import json
from typing import Any

import httpx
from typer.testing import CliRunner

from minitest_cli.commands.build import app as build_app
from tests._commit_transport import cli_context, make_settings, routed

runner = CliRunner()

CODE_PROMPT = "Add the missing import of `AppTheme` in lib/main.dart line 12."
USER_ACTION_REMEDIATION = (
    "This repository is a Python FastAPI backend service and does not contain a web "
    "frontend that can be built as a static bundle."
)
RAW_ONLY = "reaper: build heartbeat stale (>900s)"
INFRA_SAFE_SUMMARY = "The build failed because of an internal error on our side."


def _build(build_id: str, **fields: Any) -> dict[str, Any]:
    return {
        "id": build_id,
        "appId": "app-1",
        "kind": "web",
        "status": "failed",
        "createdAt": "2026-08-31T10:00:00Z",
        **fields,
    }


LIST_BODY = {
    "items": [
        _build(
            "build-code",
            kind="native",
            platform="android",
            errorClass="code",
            errorSummary="Compilation failed",
            errorRemediation="Fix the import",
            errorFixPrompt=CODE_PROMPT,
            errorRaw="error: cannot find symbol AppTheme",
        ),
        _build(
            "build-user-action",
            errorClass="user_action",
            errorRemediation=USER_ACTION_REMEDIATION,
        ),
        _build("build-raw-only", errorRaw=RAW_ONLY),
        _build("build-infra", errorClass="infra", errorSummary=INFRA_SAFE_SUMMARY),
        _build("build-ok", status="completed"),
    ],
    "total": 5,
    "page": 1,
    "pageSize": 20,
}


def _list_builds(tmp_path: Any, *, json_mode: bool) -> Any:
    settings = make_settings(tmp_path)
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return httpx.Response(200, json=LIST_BODY)

    with cli_context(settings, json_mode=json_mode), routed(handler):
        result = runner.invoke(build_app, ["list", "--status", "failed"])
    assert result.exit_code == 0, result.output
    assert seen[0].params.get_list("status") == ["failed"]
    return result


def _guidance(tmp_path: Any) -> dict[str, Any]:
    payload = json.loads(_list_builds(tmp_path, json_mode=True).stdout)
    return {item["id"]: item for item in payload["items"]}


class TestGuidanceLadder:
    def test_a_recorded_fix_prompt_wins_over_every_other_rung(self, tmp_path: Any) -> None:
        item = _guidance(tmp_path)["build-code"]
        assert item["guidance"] == {"source": "fix_prompt", "text": CODE_PROMPT}
        assert item["errorFixPrompt"] == CODE_PROMPT

    def test_remediation_is_surfaced_and_labelled_when_no_fix_prompt_exists(
        self, tmp_path: Any
    ) -> None:
        item = _guidance(tmp_path)["build-user-action"]
        assert item["guidance"] == {"source": "remediation", "text": USER_ACTION_REMEDIATION}
        assert item["errorFixPrompt"] is None

    def test_raw_builder_output_is_surfaced_and_labelled_as_raw(self, tmp_path: Any) -> None:
        item = _guidance(tmp_path)["build-raw-only"]
        assert item["guidance"] == {"source": "raw", "text": RAW_ONLY}

    def test_completed_builds_carry_no_guidance(self, tmp_path: Any) -> None:
        assert _guidance(tmp_path)["build-ok"]["guidance"] is None


class TestWithheldClasses:
    def test_infra_is_withheld_rather_than_mislabelled_as_a_fix_prompt(self, tmp_path: Any) -> None:
        item = _guidance(tmp_path)["build-infra"]
        assert item["guidance"]["source"] == "withheld"
        assert item["guidance"]["text"].startswith("This failure is not actionable")
        assert INFRA_SAFE_SUMMARY not in json.dumps(item)
        assert item["errorFixPrompt"] is None
        assert item["errorRaw"] is None

    def test_table_output_labels_each_rung_and_withholds_infra(self, tmp_path: Any) -> None:
        output = _list_builds(tmp_path, json_mode=False).output

        assert f"Fix prompt: {CODE_PROMPT}" in output
        assert "Remediation:" in output
        assert "Raw builder output:" in output
        assert "not actionable from your side" in output
        assert INFRA_SAFE_SUMMARY not in output
