"""Tests for minitest_cli.commands.screens — the exploration screen map."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import typer
from typer.testing import CliRunner

from minitest_cli.commands.screens import app as screens_app
from minitest_cli.commands.screens_format import frontier_hint, reach_label
from minitest_cli.commands.screens_helpers import dangling_edges
from minitest_cli.core.config import Settings
from minitest_cli.models import ScreenMapResponse

runner = CliRunner()


def _make_settings(tmp_path: Path, **overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "config_dir": tmp_path,
        "token": "test-token",
        "supabase_url": "https://test.supabase.co",
        "supabase_publishable_key": "test-publishable-key",
        "app_id": "app-123",
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


def _run_with_context(
    args: list[str],
    settings: Settings,
    json_mode: bool = False,
    app_flag: str | None = None,
):
    patches = [
        patch.object(typer.Context, "settings", settings, create=True),
        patch.object(typer.Context, "json_mode", json_mode, create=True),
        patch.object(typer.Context, "app_flag", app_flag, create=True),
    ]
    for p in patches:
        p.start()
    try:
        return runner.invoke(screens_app, args)
    finally:
        for p in patches:
            p.stop()


def _mock_response(status_code: int = 200, json_data: object = None) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = json.dumps(json_data) if json_data else ""
    return resp


def _mock_client(resp: MagicMock) -> AsyncMock:
    client = AsyncMock()
    client.get = AsyncMock(return_value=resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


def _node(
    key: str,
    name: str,
    depth: int,
    *,
    platform: str = "ios",
    area: str | None = "onboarding",
    blocked: str | None = None,
    outgoing: list[dict] | None = None,
) -> dict:
    return {
        "id": f"id-{key}",
        "platform": platform,
        "screenKey": key,
        "displayName": name,
        "depth": depth,
        "area": area,
        "discoveredAt": "2026-09-02T06:52:00Z",
        "firstReachedAt": "2026-09-02T06:52:00Z",
        "blockedReason": blocked,
        "gatedBy": None,
        "screenshotPath": None,
        "screenshotUrl": None,
        # NOTE: snake_case inside a camelCase envelope. That is the real wire
        # shape — testing-service embeds the DB models verbatim here.
        "outgoing": outgoing or [],
        "context": {
            "requires_auth": False,
            "persona_ref": None,
            "preconditions": [],
            "reachable_via": "walk",
            "deeplink_uri": None,
            "cheaply_reachable": True,
            "cheaply_reachable_reason": None,
        },
    }


def _edge(action: str, to: str | None, *, parked: bool = False, reason: str | None = None) -> dict:
    return {
        "action": action,
        "to_screen_key": to,
        "onward_observed": parked,
        "parked": parked,
        "parked_reason": reason,
        "parked_kind": "not_navigation" if parked else None,
        "last_verified_at": None,
        "consecutive_failures": 0,
    }


_MAP = {
    "appId": "app-123",
    "platform": None,
    "screenCount": 3,
    "screens": [
        _node(
            "welcome",
            "Welcome",
            0,
            outgoing=[
                _edge("tap 'Continue'", "settings"),
                _edge("tap 'Log in'", None, parked=True, reason="login wall"),
            ],
        ),
        _node("settings", "Settings", 1, area="settings"),
        _node("locked", "Locked area", 2, area=None, blocked="needs a paid plan"),
    ],
}

_EMPTY_MAP = {"appId": "app-123", "platform": None, "screenCount": 0, "screens": []}


class TestListScreensCommand:
    def test_list_hits_correct_endpoint(self, tmp_path: Path) -> None:
        client = _mock_client(_mock_response(200, _MAP))
        with patch("minitest_cli.commands.screens_helpers.ApiClient", return_value=client):
            result = _run_with_context(["list"], _make_settings(tmp_path), json_mode=True)

        assert result.exit_code == 0
        assert client.get.call_args[0][0] == "/api/v1/apps/app-123/screens"

    def test_list_platform_filter_sent_as_param(self, tmp_path: Path) -> None:
        client = _mock_client(_mock_response(200, _MAP))
        with patch("minitest_cli.commands.screens_helpers.ApiClient", return_value=client):
            result = _run_with_context(
                ["list", "--platform", "ios"], _make_settings(tmp_path), json_mode=True
            )

        assert result.exit_code == 0
        assert client.get.call_args[1]["params"]["platform"] == "ios"

    def test_list_omits_platform_param_when_unset(self, tmp_path: Path) -> None:
        client = _mock_client(_mock_response(200, _MAP))
        with patch("minitest_cli.commands.screens_helpers.ApiClient", return_value=client):
            _run_with_context(["list"], _make_settings(tmp_path), json_mode=True)

        assert client.get.call_args[1]["params"] == {}

    def test_list_human_mode_renders_every_screen_name(self, tmp_path: Path) -> None:
        client = _mock_client(_mock_response(200, _MAP))
        with patch("minitest_cli.commands.screens_helpers.ApiClient", return_value=client):
            result = _run_with_context(["list"], _make_settings(tmp_path))

        assert result.exit_code == 0
        for name in ("Welcome", "Settings", "Locked area"):
            assert name in result.output

    def test_list_area_filter_narrows_output(self, tmp_path: Path) -> None:
        client = _mock_client(_mock_response(200, _MAP))
        with patch("minitest_cli.commands.screens_helpers.ApiClient", return_value=client):
            result = _run_with_context(
                ["list", "--area", "settings"], _make_settings(tmp_path), json_mode=True
            )

        data = json.loads(result.output)
        assert [s["displayName"] for s in data["screens"]] == ["Settings"]
        # The count must agree with the screens beside it, not the server total.
        assert data["screenCount"] == 1

    def test_list_blocked_filter_keeps_only_blocked(self, tmp_path: Path) -> None:
        client = _mock_client(_mock_response(200, _MAP))
        with patch("minitest_cli.commands.screens_helpers.ApiClient", return_value=client):
            result = _run_with_context(
                ["list", "--blocked"], _make_settings(tmp_path), json_mode=True
            )

        data = json.loads(result.output)
        assert [s["displayName"] for s in data["screens"]] == ["Locked area"]

    def test_list_tree_mode_renders_edge_actions(self, tmp_path: Path) -> None:
        client = _mock_client(_mock_response(200, _MAP))
        with patch("minitest_cli.commands.screens_helpers.ApiClient", return_value=client):
            result = _run_with_context(["list", "--tree"], _make_settings(tmp_path))

        assert result.exit_code == 0
        assert "tap 'Continue'" in result.output
        assert "parked" in result.output

    def test_list_empty_map_explains_no_crawl_has_run(self, tmp_path: Path) -> None:
        client = _mock_client(_mock_response(200, _EMPTY_MAP))
        with patch("minitest_cli.commands.screens_helpers.ApiClient", return_value=client):
            result = _run_with_context(["list"], _make_settings(tmp_path))

        assert result.exit_code == 0
        assert "until a crawl has run" in result.output

    def test_list_filtered_to_empty_does_not_claim_no_crawl(self, tmp_path: Path) -> None:
        client = _mock_client(_mock_response(200, _MAP))
        with patch("minitest_cli.commands.screens_helpers.ApiClient", return_value=client):
            result = _run_with_context(["list", "--area", "nope"], _make_settings(tmp_path))

        assert result.exit_code == 0
        assert "3 screen(s) mapped" in result.output
        assert "until a crawl has run" not in result.output

    def test_list_404_exits_4(self, tmp_path: Path) -> None:
        client = _mock_client(_mock_response(404, {"detail": "App not found"}))
        with patch("minitest_cli.commands.screens_helpers.ApiClient", return_value=client):
            result = _run_with_context(["list"], _make_settings(tmp_path))

        assert result.exit_code == 4

    def test_list_network_error_exits_3(self, tmp_path: Path) -> None:
        client = AsyncMock()
        client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        with patch("minitest_cli.commands.screens_helpers.ApiClient", return_value=client):
            result = _run_with_context(["list"], _make_settings(tmp_path))

        assert result.exit_code == 3

    def test_list_requires_auth(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path, token=None)
        with patch("minitest_cli.core.auth.require_auth", side_effect=typer.Exit(code=2)):
            result = _run_with_context(["list"], settings)

        assert result.exit_code == 2

    def test_list_uses_app_flag_over_settings(self, tmp_path: Path) -> None:
        client = _mock_client(_mock_response(200, _MAP))
        with patch("minitest_cli.commands.screens_helpers.ApiClient", return_value=client):
            _run_with_context(
                ["list"],
                _make_settings(tmp_path, app_id=None),
                json_mode=True,
                app_flag="other-app",
            )

        assert client.get.call_args[0][0] == "/api/v1/apps/other-app/screens"


class TestGetScreenCommand:
    def test_get_matches_by_display_name_case_insensitively(self, tmp_path: Path) -> None:
        client = _mock_client(_mock_response(200, _MAP))
        with patch("minitest_cli.commands.screens_helpers.ApiClient", return_value=client):
            result = _run_with_context(["get", "wELCome"], _make_settings(tmp_path))

        assert result.exit_code == 0
        assert "Welcome" in result.output

    def test_get_matches_by_screen_key(self, tmp_path: Path) -> None:
        client = _mock_client(_mock_response(200, _MAP))
        with patch("minitest_cli.commands.screens_helpers.ApiClient", return_value=client):
            result = _run_with_context(
                ["get", "settings"], _make_settings(tmp_path), json_mode=True
            )

        assert result.exit_code == 0
        assert json.loads(result.output)["screenKey"] == "settings"

    def test_get_unknown_screen_exits_4(self, tmp_path: Path) -> None:
        client = _mock_client(_mock_response(200, _MAP))
        with patch("minitest_cli.commands.screens_helpers.ApiClient", return_value=client):
            result = _run_with_context(["get", "nope"], _make_settings(tmp_path))

        assert result.exit_code == 4

    def test_get_reports_every_platform_match(self, tmp_path: Path) -> None:
        both = {
            **_MAP,
            "screenCount": 2,
            "screens": [
                _node("welcome", "Welcome", 0, platform="ios"),
                _node("welcome", "Welcome", 0, platform="android"),
            ],
        }
        client = _mock_client(_mock_response(200, both))
        with patch("minitest_cli.commands.screens_helpers.ApiClient", return_value=client):
            result = _run_with_context(["get", "welcome"], _make_settings(tmp_path))

        assert result.exit_code == 0
        assert "2 screens match" in result.output

    def test_get_renders_blocked_reason(self, tmp_path: Path) -> None:
        client = _mock_client(_mock_response(200, _MAP))
        with patch("minitest_cli.commands.screens_helpers.ApiClient", return_value=client):
            result = _run_with_context(["get", "Locked area"], _make_settings(tmp_path))

        assert "needs a paid plan" in result.output


class TestWireShape:
    """Guards the camelCase-envelope / snake_case-nested seam.

    ``outgoing`` and ``context`` are embedded DB models with no alias
    generator, so they arrive snake_case inside a camelCase envelope. Making
    them ``CamelModel`` would still *parse* (``populate_by_name`` accepts the
    field name), which is what makes the mistake easy to ship unnoticed — but
    ``--json`` would then emit ``toScreenKey`` where the API emits
    ``to_screen_key``. So the binding assertion is on the emitted keys.
    """

    def test_snake_case_edges_and_context_parse(self) -> None:
        parsed = ScreenMapResponse.model_validate(_MAP)
        welcome = parsed.screens[0]

        assert len(welcome.outgoing) == 2
        assert welcome.outgoing[0].to_screen_key == "settings"
        assert welcome.outgoing[1].parked is True
        assert welcome.outgoing[1].parked_reason == "login wall"
        assert welcome.context is not None
        assert welcome.context.reachable_via == "walk"
        assert welcome.context.cheaply_reachable is True

    def test_json_output_keeps_nested_keys_snake_case(self, tmp_path: Path) -> None:
        """--json must round-trip the API's shape, not re-case the nested models."""
        client = _mock_client(_mock_response(200, _MAP))
        with patch("minitest_cli.commands.screens_helpers.ApiClient", return_value=client):
            result = _run_with_context(["list"], _make_settings(tmp_path), json_mode=True)

        data = json.loads(result.output)
        edge = data["screens"][0]["outgoing"][0]
        context = data["screens"][0]["context"]

        # Envelope stays camelCase...
        assert "screenKey" in data["screens"][0]
        assert "displayName" in data["screens"][0]
        # ...while the embedded DB models stay snake_case, as the API serves them.
        assert "to_screen_key" in edge
        assert "toScreenKey" not in edge
        assert "parked_reason" in edge
        assert "requires_auth" in context
        assert "requiresAuth" not in context

    def test_unknown_fields_are_tolerated(self) -> None:
        payload = json.loads(json.dumps(_MAP))
        payload["screens"][0]["somethingNew"] = "x"
        payload["screens"][0]["outgoing"][0]["new_edge_field"] = 1

        parsed = ScreenMapResponse.model_validate(payload)
        assert parsed.screens[0].outgoing[0].action == "tap 'Continue'"


class TestFrontierReporting:
    def test_dangling_edges_are_detected(self) -> None:
        parsed = ScreenMapResponse.model_validate(_MAP)
        # 'welcome' -> 'settings' resolves; nothing else is followed.
        assert dangling_edges(parsed.screens) == []

        broken = json.loads(json.dumps(_MAP))
        broken["screens"][0]["outgoing"][0]["to_screen_key"] = "ghost"
        dangling = dangling_edges(ScreenMapResponse.model_validate(broken).screens)
        assert len(dangling) == 1
        assert dangling[0][1].to_screen_key == "ghost"

    def test_hint_reports_parked_blocked_and_dangling(self) -> None:
        parsed = ScreenMapResponse.model_validate(_MAP)
        hint = frontier_hint(parsed.screens, parsed.screens)

        assert "1 parked edge(s)" in hint
        assert "1 blocked screen(s)" in hint

    def test_hint_does_not_blame_filtering_for_dangling(self) -> None:
        parsed = ScreenMapResponse.model_validate(_MAP)
        # Show only 'Welcome'; its destination is filtered out but not missing.
        hint = frontier_hint(parsed.screens[:1], parsed.screens)

        assert "no row in the map" not in hint

    def test_reach_label_flags_auth_and_cost(self) -> None:
        payload = json.loads(json.dumps(_MAP))
        ctx = payload["screens"][0]["context"]
        ctx["requires_auth"] = True
        ctx["persona_ref"] = "parent"
        ctx["cheaply_reachable"] = False
        ctx["cheaply_reachable_reason"] = "server-side state"

        node = ScreenMapResponse.model_validate(payload).screens[0]
        label = reach_label(node)
        assert "auth:parent" in label
        assert "costly" in label
