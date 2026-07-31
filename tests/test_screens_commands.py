"""Tests for minitest_cli.commands.screens — `screens list`."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import typer
from typer.testing import CliRunner

from minitest_cli.commands.screens import app as screens_app
from minitest_cli.core.config import Settings

runner = CliRunner()


def _make_settings(tmp_path, **overrides):
    defaults = {
        "config_dir": tmp_path,
        "token": "test-token",
        "supabase_url": "https://test.supabase.co",
        "supabase_publishable_key": "test-key",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _run_with_context(args, settings, json_mode=False):
    patches = [
        patch.object(typer.Context, "settings", settings, create=True),
        patch.object(typer.Context, "json_mode", json_mode, create=True),
        patch.object(typer.Context, "app_flag", None, create=True),
    ]
    for p in patches:
        p.start()
    try:
        return runner.invoke(screens_app, args)
    finally:
        for p in patches:
            p.stop()


def _mock_response(status_code=200, json_data=None):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = json.dumps(json_data) if json_data is not None else ""
    return resp


def _mock_client(resp):
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(return_value=resp)
    return client


_MAP = {
    "appId": "app-1",
    "platform": "android",
    "screenCount": 2,
    "screens": [
        {
            "id": "s-1",
            "screenKey": "home",
            "displayName": "Home",
            "depth": 0,
            "area": "home",
            "blockedReason": None,
            "screenshotUrl": "https://signed.example/home.png",
            "outgoing": [{"action": "tap 'Shop'", "toScreenKey": "browse", "parked": False}],
        },
        {
            "id": "s-2",
            "screenKey": "promo",
            "displayName": "Promo",
            "depth": 1,
            "area": "checkout",
            "blockedReason": "needs a promo code only the customer has",
            "screenshotUrl": None,
            "outgoing": [
                {"action": "tap 'Refer'", "parked": True, "parkedReason": "no second account"}
            ],
        },
    ],
}


class TestListScreens:
    def test_human_output_lists_every_node(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client(_mock_response(200, _MAP))

        with patch("minitest_cli.commands.screens.ApiClient", return_value=client):
            result = _run_with_context(["list", "--app", "app-1"], settings)

        assert result.exit_code == 0, result.output
        assert "Home" in result.output
        assert "Promo" in result.output
        client.get.assert_called_once_with("/api/v1/apps/app-1/screens", params=None)

    def test_a_blocked_node_shows_its_reason_not_a_boolean(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client(_mock_response(200, _MAP))

        with patch("minitest_cli.commands.screens.ApiClient", return_value=client):
            result = _run_with_context(["list", "--app", "app-1"], settings)

        assert "promo code" in result.output
        assert "True" not in result.output

    def test_platform_filter_is_passed_through(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client(_mock_response(200, _MAP))

        with patch("minitest_cli.commands.screens.ApiClient", return_value=client):
            result = _run_with_context(
                ["list", "--app", "app-1", "--platform", "android"], settings
            )

        assert result.exit_code == 0, result.output
        client.get.assert_called_once_with(
            "/api/v1/apps/app-1/screens", params={"platform": "android"}
        )

    def test_json_returns_the_full_record(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client(_mock_response(200, _MAP))

        with patch("minitest_cli.commands.screens.ApiClient", return_value=client):
            result = _run_with_context(["list", "--app", "app-1"], settings, json_mode=True)

        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        # --json is the machine surface: it must carry the whole record, not
        # the human table's summary.
        assert payload["screens"][0]["screenshotUrl"].startswith("https://")
        assert payload["screens"][1]["outgoing"][0]["parked"] is True

    def test_unknown_platform_is_rejected_before_any_network_call(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client(_mock_response(200, _MAP))

        with patch("minitest_cli.commands.screens.ApiClient", return_value=client):
            result = _run_with_context(
                ["list", "--app", "app-1", "--platform", "windows"], settings
            )

        assert result.exit_code != 0
        assert "android, ios" in result.output
        client.get.assert_not_called()

    def test_an_empty_map_exits_not_found(self, tmp_path):
        settings = _make_settings(tmp_path)
        empty = {**_MAP, "screenCount": 0, "screens": []}
        client = _mock_client(_mock_response(200, empty))

        with patch("minitest_cli.commands.screens.ApiClient", return_value=client):
            result = _run_with_context(["list", "--app", "app-1"], settings)

        assert result.exit_code == 4

    def test_a_missing_app_exits_not_found(self, tmp_path):
        settings = _make_settings(tmp_path)
        client = _mock_client(_mock_response(404, {"detail": "no such app"}))

        with patch("minitest_cli.commands.screens.ApiClient", return_value=client):
            result = _run_with_context(["list", "--app", "nope"], settings)

        assert result.exit_code == 4


class TestNoWriteSurface:
    def test_the_cli_exposes_no_screen_write_command(self):
        # The crawl writes in-process on the testing-service side; a CLI write
        # path here would be speculative API nobody calls.
        result = runner.invoke(screens_app, ["--help"])
        assert result.exit_code == 0
        for verb in ("record", "create", "upsert", "write", "delete"):
            assert verb not in result.output
