"""Tests for draft-feature commands (list, create, show, apply, delete)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import typer
from typer.testing import CliRunner

from minitest_cli.commands.draft_feature import app as df_app
from minitest_cli.core.config import Settings

runner = CliRunner()

_FEATURE_UUID = "11111111-2222-3333-4444-555555555555"
_BASE = "/api/v1/apps/app-123/draft-features"

_FEATURE = {
    "id": "b1",
    "tenantId": "t1",
    "appId": "a1",
    "title": "Checkout",
    "description": "New flow",
    "status": "open",
    "rebaseState": "conflicts",
    "rebasedToMainRev": 3,
    "sourceRefs": [],
    "createdAt": "2026-05-22T10:00:00Z",
    "updatedAt": "2026-05-22T10:00:00Z",
    "mergedAt": None,
}


def _make_settings(tmp_path):
    return Settings(
        config_dir=tmp_path,
        token="test-token",
        supabase_url="https://test.supabase.co",
        supabase_publishable_key="test-publishable-key",
        app_id="app-123",
    )


def _run(args, settings, json_mode=False):
    patches = [
        patch.object(typer.Context, "settings", settings, create=True),
        patch.object(typer.Context, "json_mode", json_mode, create=True),
        patch.object(typer.Context, "app_flag", None, create=True),
    ]
    for p in patches:
        p.start()
    try:
        return runner.invoke(df_app, args)
    finally:
        for p in patches:
            p.stop()


def _mock_response(status_code=200, json_data=None):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = json.dumps(json_data) if json_data else ""
    return resp


def _mock_client(get=None, post=None, delete=None):
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(return_value=get)
    client.post = AsyncMock(return_value=post)
    client.delete = AsyncMock(return_value=delete)
    return client


def _text(result) -> str:
    """Console output as one whitespace-normalised string (rich wraps at 80 cols)."""
    combined = result.output + (result.stderr if result.stderr_bytes else "")
    return " ".join(combined.split())


def _stdout(result) -> str:
    """Stdout only — diagnostics go to stderr, so this is the machine-readable half."""
    return " ".join(result.stdout.split())


class TestList:
    def test_list_repeats_the_status_query_param_per_value(self, tmp_path):
        client = _mock_client(get=_mock_response(200, [_FEATURE]))
        with patch("minitest_cli.commands.draft_feature.ApiClient", return_value=client):
            result = _run(
                ["list", "--status", "open", "--status", "merging"],
                _make_settings(tmp_path),
                json_mode=True,
            )
        assert result.exit_code == 0
        assert client.get.await_args.args[0] == _BASE
        assert client.get.await_args.kwargs["params"] == {"status": ["open", "merging"]}

    def test_list_without_status_sends_no_filter(self, tmp_path):
        client = _mock_client(get=_mock_response(200, [_FEATURE]))
        with patch("minitest_cli.commands.draft_feature.ApiClient", return_value=client):
            result = _run(["list"], _make_settings(tmp_path), json_mode=True)
        assert result.exit_code == 0
        assert client.get.await_args.kwargs["params"] == {}

    def test_list_table_shows_id_status_and_rebase_state(self, tmp_path):
        client = _mock_client(get=_mock_response(200, [_FEATURE]))
        with patch("minitest_cli.commands.draft_feature.ApiClient", return_value=client):
            result = _run(["list"], _make_settings(tmp_path))
        assert result.exit_code == 0
        stdout = _stdout(result)
        assert "b1" in stdout
        assert "open" in stdout
        assert "conflicts" in stdout


class TestCreate:
    def test_create_sends_title_and_description(self, tmp_path):
        client = _mock_client(post=_mock_response(201, _FEATURE))
        with patch("minitest_cli.commands.draft_feature.ApiClient", return_value=client):
            result = _run(
                ["create", "--title", "Checkout", "--description", "New flow"],
                _make_settings(tmp_path),
                json_mode=True,
            )
        assert result.exit_code == 0
        assert client.post.await_args.args[0] == _BASE
        assert client.post.await_args.kwargs["json"] == {
            "title": "Checkout",
            "description": "New flow",
        }

    def test_create_omits_description_when_not_given(self, tmp_path):
        client = _mock_client(post=_mock_response(201, _FEATURE))
        with patch("minitest_cli.commands.draft_feature.ApiClient", return_value=client):
            result = _run(
                ["create", "--title", "Checkout"], _make_settings(tmp_path), json_mode=True
            )
        assert result.exit_code == 0
        assert client.post.await_args.kwargs["json"] == {"title": "Checkout"}

    def test_create_prints_the_new_id(self, tmp_path):
        client = _mock_client(post=_mock_response(201, _FEATURE))
        with patch("minitest_cli.commands.draft_feature.ApiClient", return_value=client):
            result = _run(["create", "--title", "Checkout"], _make_settings(tmp_path))
        assert result.exit_code == 0
        assert "id: b1" in _stdout(result)


class TestShow:
    _CHANGESET = {
        "draftFeature": _FEATURE,
        "mainRev": 7,
        "ops": [{"op": "story.delete", "story_id": "s1"}],
    }
    _SUITE = {
        "stories": [{"storyId": "s1", "slotId": "m1", "origin": "override", "ordinal": 1}],
        "edges": [],
    }

    def test_show_diff_reads_the_changeset_endpoint(self, tmp_path):
        client = _mock_client(get=_mock_response(200, self._CHANGESET))
        with patch("minitest_cli.commands.draft_feature_show.ApiClient", return_value=client):
            result = _run(["show", _FEATURE_UUID], _make_settings(tmp_path), json_mode=True)
        assert result.exit_code == 0
        assert client.get.await_args.args[0] == f"{_BASE}/{_FEATURE_UUID}/changeset"

    def test_show_effective_reads_the_effective_suite_endpoint(self, tmp_path):
        client = _mock_client(get=_mock_response(200, self._SUITE))
        with patch("minitest_cli.commands.draft_feature_show.ApiClient", return_value=client):
            result = _run(
                ["show", _FEATURE_UUID, "--view", "effective"],
                _make_settings(tmp_path),
                json_mode=True,
            )
        assert result.exit_code == 0
        assert client.get.await_args.args[0] == f"{_BASE}/{_FEATURE_UUID}/effective-suite"

    def test_show_diff_puts_main_rev_on_stdout(self, tmp_path):
        client = _mock_client(get=_mock_response(200, self._CHANGESET))
        with patch("minitest_cli.commands.draft_feature_show.ApiClient", return_value=client):
            result = _run(["show", _FEATURE_UUID], _make_settings(tmp_path))
        assert result.exit_code == 0
        assert "mainRev 7" in _stdout(result)

    def test_show_rejects_a_non_uuid_id_before_calling_the_api(self, tmp_path):
        client = _mock_client()
        with patch("minitest_cli.commands.draft_feature_show.ApiClient", return_value=client):
            result = _run(["show", "not-a-uuid"], _make_settings(tmp_path))
        assert result.exit_code == 1
        client.get.assert_not_awaited()


class TestApply:
    _RESULT = {
        "draftFeatureId": _FEATURE_UUID,
        "created": {"tmp-1": "s9"},
        "touchedStoryIds": ["s9"],
        "mainRev": 7,
    }
    _BODY = {
        "expectedMainRev": 7,
        "ops": [{"op": "story.create", "tmpId": "tmp-1", "fields": {"name": "Pay"}}],
    }

    def _write_changeset(self, tmp_path, content: str):
        path = tmp_path / "changeset.json"
        path.write_text(content)
        return path

    def test_apply_posts_the_file_body_to_the_apply_endpoint(self, tmp_path):
        path = self._write_changeset(tmp_path, json.dumps(self._BODY))
        client = _mock_client(post=_mock_response(200, self._RESULT))
        with patch("minitest_cli.commands.draft_feature_apply.ApiClient", return_value=client):
            result = _run(
                ["apply", _FEATURE_UUID, "--changeset", str(path)],
                _make_settings(tmp_path),
                json_mode=True,
            )
        assert result.exit_code == 0
        assert client.post.await_args.args[0] == f"{_BASE}/{_FEATURE_UUID}/apply"
        assert client.post.await_args.kwargs["json"] == self._BODY

    def test_apply_reports_the_created_tmp_id_mapping_and_cursor(self, tmp_path):
        path = self._write_changeset(tmp_path, json.dumps(self._BODY))
        client = _mock_client(post=_mock_response(200, self._RESULT))
        with patch("minitest_cli.commands.draft_feature_apply.ApiClient", return_value=client):
            result = _run(
                ["apply", _FEATURE_UUID, "--changeset", str(path)], _make_settings(tmp_path)
            )
        assert result.exit_code == 0
        stdout = _stdout(result)
        assert "tmp-1" in stdout
        assert "s9" in stdout
        assert "mainRev 7" in stdout

    def test_apply_missing_file_reports_a_readable_error(self, tmp_path):
        client = _mock_client()
        with patch("minitest_cli.commands.draft_feature_apply.ApiClient", return_value=client):
            result = _run(
                ["apply", _FEATURE_UUID, "--changeset", str(tmp_path / "absent.json")],
                _make_settings(tmp_path),
            )
        assert result.exit_code == 1
        assert "Could not read changeset file" in _text(result)
        client.post.assert_not_awaited()

    def test_apply_invalid_json_reports_a_readable_error(self, tmp_path):
        path = self._write_changeset(tmp_path, "{not json")
        client = _mock_client()
        with patch("minitest_cli.commands.draft_feature_apply.ApiClient", return_value=client):
            result = _run(
                ["apply", _FEATURE_UUID, "--changeset", str(path)], _make_settings(tmp_path)
            )
        assert result.exit_code == 1
        assert "is not valid JSON" in _text(result)
        client.post.assert_not_awaited()

    def test_apply_rejects_a_json_array_before_calling_the_api(self, tmp_path):
        path = self._write_changeset(tmp_path, json.dumps([{"op": "story.delete"}]))
        client = _mock_client()
        with patch("minitest_cli.commands.draft_feature_apply.ApiClient", return_value=client):
            result = _run(
                ["apply", _FEATURE_UUID, "--changeset", str(path)], _make_settings(tmp_path)
            )
        assert result.exit_code == 1
        assert "must contain a JSON object" in _text(result)
        client.post.assert_not_awaited()

    def test_apply_conflict_surfaces_the_server_message(self, tmp_path):
        path = self._write_changeset(tmp_path, json.dumps(self._BODY))
        conflict = _mock_response(409, {"detail": "main suite moved to rev 5 since rev 3"})
        client = _mock_client(post=conflict)
        with patch("minitest_cli.commands.draft_feature_apply.ApiClient", return_value=client):
            result = _run(
                ["apply", _FEATURE_UUID, "--changeset", str(path)], _make_settings(tmp_path)
            )
        assert result.exit_code == 3
        assert "main suite moved to rev 5 since rev 3" in _text(result)


class TestDelete:
    def test_delete_requires_force(self, tmp_path):
        client = _mock_client()
        with patch("minitest_cli.commands.draft_feature.ApiClient", return_value=client):
            result = _run(["delete", _FEATURE_UUID], _make_settings(tmp_path))
        assert result.exit_code == 1
        client.delete.assert_not_awaited()

    def test_delete_reports_the_status_the_server_returned(self, tmp_path):
        abandoned = _mock_response(200, {**_FEATURE, "status": "abandoned"})
        client = _mock_client(delete=abandoned)
        with patch("minitest_cli.commands.draft_feature.ApiClient", return_value=client):
            result = _run(["delete", _FEATURE_UUID, "--force"], _make_settings(tmp_path))
        assert result.exit_code == 0
        assert client.delete.await_args.args[0] == f"{_BASE}/{_FEATURE_UUID}"
        assert "status: abandoned" in _text(result)

    def test_delete_not_found_exits_four_with_the_server_message(self, tmp_path):
        client = _mock_client(delete=_mock_response(404, {"detail": "Draft feature not found."}))
        with patch("minitest_cli.commands.draft_feature.ApiClient", return_value=client):
            result = _run(["delete", _FEATURE_UUID, "--force"], _make_settings(tmp_path))
        assert result.exit_code == 4
        assert "Draft feature not found." in _text(result)
