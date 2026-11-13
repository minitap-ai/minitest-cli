"""Tests for ``minitest screens`` over the screen-tree API.

Every command runs a real httpx request cycle against a recorded
``GET /api/v1/apps/{app_id}/screen-tree`` response (``fixtures/screen_tree.json``):
an android tree rooted at a notification prompt, with tree edges, cross-links,
signed-out and ``swiper`` walks, pending/blocked/skipped elements, a transition
into a screen with no row, and a detached screen; plus a two-screen ios tree.
"""

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import typer
from click.testing import Result
from typer.testing import CliRunner

from minitest_cli.commands.screens import app as screens_app
from tests._commit_transport import cli_context, make_settings, routed

runner = CliRunner()

FIXTURE: dict[str, Any] = json.loads(
    (Path(__file__).parent / "fixtures" / "screen_tree.json").read_text()
)
APP_ID = "a0d9820f-5136-4f70-b46b-e5966f56bfb5"
TREE_PATH = f"/api/v1/apps/{APP_ID}/screen-tree"


def _serve(payload: dict[str, Any], seen: list[httpx.Request] | None = None) -> Callable:
    """Answer like testing-service: honour ``?platform=`` server-side."""

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        if request.url.path != TREE_PATH:
            return httpx.Response(404, json={"detail": "Not found"})
        platform = request.url.params.get("platform")
        trees = [t for t in payload["trees"] if platform is None or t["platform"] == platform]
        return httpx.Response(200, json={**payload, "trees": trees})

    return handler


def _invoke(
    tmp_path: Path,
    args: list[str],
    *,
    json_mode: bool = False,
    handler: Callable | None = None,
) -> Result:
    settings = make_settings(tmp_path)
    with routed(handler or _serve(FIXTURE)), cli_context(settings, json_mode=json_mode):
        return runner.invoke(screens_app, args, env={"COLUMNS": "200"})


def _row(output: str, screen: str) -> list[str]:
    for line in output.splitlines():
        cells = [c.strip() for c in line.split("│")[1:-1]]
        if len(cells) > 1 and cells[1] == screen:
            return cells
    raise AssertionError(f"no table row for {screen!r} in:\n{output}")


def _line(output: str, needle: str) -> str:
    matches = [line for line in output.splitlines() if needle in line]
    assert len(matches) == 1, f"expected one line with {needle!r}, got {matches}"
    return matches[0]


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" │├└─"))


class TestScreenTreeRequest:
    def test_list_calls_screen_tree_without_platform(self, tmp_path: Path) -> None:
        seen: list[httpx.Request] = []
        result = _invoke(tmp_path, ["list"], json_mode=True, handler=_serve(FIXTURE, seen))

        assert result.exit_code == 0
        assert [r.url.path for r in seen] == [TREE_PATH]
        assert "platform" not in seen[0].url.params

    def test_platform_is_sent_and_selects_that_tree(self, tmp_path: Path) -> None:
        seen: list[httpx.Request] = []
        result = _invoke(tmp_path, ["list", "--platform", "ios"], handler=_serve(FIXTURE, seen))

        assert result.exit_code == 0
        assert seen[0].url.params["platform"] == "ios"
        assert "Screens (ios)" in result.output
        assert "Screens (android)" not in result.output

    def test_platform_is_filtered_client_side_too(self, tmp_path: Path) -> None:
        def ignores_platform(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=FIXTURE)

        result = _invoke(
            tmp_path, ["list", "--platform", "android"], json_mode=True, handler=ignores_platform
        )

        assert [t["platform"] for t in json.loads(result.output)["trees"]] == ["android"]

    def test_404_exits_4(self, tmp_path: Path) -> None:
        result = _invoke(
            tmp_path,
            ["list"],
            handler=lambda _: httpx.Response(404, json={"detail": "App not found"}),
        )

        assert result.exit_code == 4

    def test_network_error_exits_3(self, tmp_path: Path) -> None:
        def refuse(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused", request=request)

        result = _invoke(tmp_path, ["list"], handler=refuse)

        assert result.exit_code == 3

    def test_requires_auth(self, tmp_path: Path) -> None:
        with patch("minitest_cli.core.auth.require_auth", side_effect=typer.Exit(code=2)):
            result = _invoke(tmp_path, ["list"])

        assert result.exit_code == 2


class TestListTable:
    def test_rows_show_depth_parent_element_and_counts(self, tmp_path: Path) -> None:
        result = _invoke(tmp_path, ["list", "--platform", "android"])

        assert result.exit_code == 0
        assert _row(result.output, "Notification permission") == [
            "0", "Notification permission", "onboarding", "—", "2", "0", "0", "0",
        ]  # fmt: skip
        assert _row(result.output, "Sign in")[3] == "(auto)"
        assert _row(result.output, "Google sign-in consent") == [
            "2", "Google sign-in consent", "auth", "LOG IN WITH GOOGLE", "1", "0", "1", "0",
        ]  # fmt: skip
        assert _row(result.output, "Listing detail") == [
            "3", "Listing detail", "main", "Listing card", "1", "0", "0", "1",
        ]  # fmt: skip
        assert _row(result.output, "Legacy orphan") == [
            "—", "Legacy orphan", "—", "—", "0", "1", "0", "0",
        ]  # fmt: skip

    def test_rows_follow_server_order(self, tmp_path: Path) -> None:
        result = _invoke(tmp_path, ["list", "--platform", "android"])

        names = [s["displayName"] for s in FIXTURE["trees"][0]["screens"]]
        positions = [result.output.index(f"│ {name} ") for name in names]
        assert positions == sorted(positions)

    def test_footer_reports_totals_and_detached(self, tmp_path: Path) -> None:
        result = _invoke(tmp_path, ["list", "--platform", "android"])

        assert (
            "Totals: 8 screen(s) · 12 explored · 4 pending · 2 blocked · 2 skipped · 1 detached"
            in result.output
        )
        assert "root: Notification permission" in result.output

    def test_every_tree_is_listed_one_after_another(self, tmp_path: Path) -> None:
        result = _invoke(tmp_path, ["list"])

        android = result.output.index("Screens (android) — 8 screen(s)")
        ios = result.output.index("Screens (ios) — 2 screen(s), root: Welcome")
        assert android < ios
        assert "Totals: 2 screen(s) · 1 explored · 1 pending" in result.output[ios:]

    def test_blocked_keeps_screens_with_a_blocked_transition(self, tmp_path: Path) -> None:
        result = _invoke(tmp_path, ["list", "--blocked"])

        assert result.exit_code == 0
        assert "Screens (android) — 2 of 8 screen(s)" in result.output
        assert _row(result.output, "Google sign-in consent")[6] == "1"
        assert _row(result.output, "Phone verification")[6] == "1"
        assert "│ Home " not in result.output
        assert "Screens (ios)" not in result.output
        assert "Totals: 2 screen(s) · 1 explored · 1 pending · 2 blocked · 0 skipped" in (
            result.output
        )

    def test_area_filter_is_case_insensitive(self, tmp_path: Path) -> None:
        result = _invoke(tmp_path, ["list", "--area", "MAIN"])

        assert "Screens (android) — 2 of 8 screen(s)" in result.output
        assert _row(result.output, "Home")[3] == "Skip"
        assert _row(result.output, "Listing detail")[0] == "3"

    def test_empty_tree_explains_no_crawl_has_run(self, tmp_path: Path) -> None:
        empty = {"appId": FIXTURE["appId"], "trees": []}
        result = _invoke(tmp_path, ["list"], handler=_serve(empty))

        assert result.exit_code == 0
        assert "until a crawl has run" in result.output

    def test_filtered_to_nothing_does_not_claim_no_crawl(self, tmp_path: Path) -> None:
        result = _invoke(tmp_path, ["list", "--area", "checkout"])

        assert result.exit_code == 0
        assert "10 screen(s) mapped, but none match --area checkout." in result.output
        assert "until a crawl has run" not in result.output


class TestListTree:
    def test_children_hang_off_tree_edges_labelled_by_element(self, tmp_path: Path) -> None:
        result = _invoke(tmp_path, ["list", "--tree", "--platform", "android"])
        out = result.output

        assert result.exit_code == 0
        root = _line(out, "Notification permission (onboarding)")
        sign_in = _line(out, "(auto) → Sign in (auth)")
        home = _line(out, "Skip → Home (main)")
        listing = _line(out, "Listing card as swiper → Listing detail (main)")
        assert _indent(root) < _indent(sign_in) < _indent(home) < _indent(listing)
        assert "LOG IN WITH GOOGLE → Google sign-in consent (auth) 1 blocked" in out
        assert "Continue with phone → Phone verification (auth) 1 pending 1 blocked" in out

    def test_account_is_shown_only_when_signed_in(self, tmp_path: Path) -> None:
        result = _invoke(tmp_path, ["list", "--tree", "--platform", "android"])

        assert "Skip as" not in _line(result.output, "→ Home (main)")
        assert "Profile as swiper → Profile (account)" in result.output

    def test_cross_links_are_marked_once_and_not_expanded(self, tmp_path: Path) -> None:
        result = _invoke(tmp_path, ["list", "--tree", "--platform", "android"])
        out = result.output

        assert out.count("↪ Home (also via Back as swiper)") == 1
        assert out.count("↪ Home (also via Skip as swiper)") == 1
        assert out.count("↪ Sign in (also via Allow)") == 1
        assert out.count("↪ Sign in (also via Cancel)") == 1
        assert out.count("↪ Sign in (also via Log out as swiper)") == 1
        assert out.count("Listing detail (main)") == 1
        back = _line(out, "also via Back")
        assert _indent(back) > _indent(_line(out, "→ Listing detail (main)"))

    def test_cross_link_to_a_screen_without_a_row_is_flagged(self, tmp_path: Path) -> None:
        result = _invoke(tmp_path, ["list", "--tree", "--platform", "android"])

        assert "↪ help center (also via Help as swiper, no screen row)" in result.output

    def test_detached_screens_are_listed_last(self, tmp_path: Path) -> None:
        result = _invoke(tmp_path, ["list", "--tree", "--platform", "android"])
        lines = result.output.splitlines()

        detached = lines.index(_line(result.output, "Detached (not reachable from the root)"))
        assert "Legacy orphan 1 pending" in lines[detached + 1]
        assert lines[detached + 2].startswith("Totals: 8 screen(s)")

    def test_tree_without_root_lists_every_screen_as_detached(self, tmp_path: Path) -> None:
        payload = copy.deepcopy(FIXTURE)
        ios = payload["trees"][1]
        ios["rootScreenKey"] = None
        ios["detachedScreenKeys"] = ["welcome", "sign in"]
        for screen in ios["screens"]:
            screen.update(depth=None, parentTransitionId=None, childTransitionIds=[])
        for transition in ios["transitions"]:
            transition["isTreeEdge"] = False

        result = _invoke(tmp_path, ["list", "--tree", "--platform", "ios"], handler=_serve(payload))

        assert "root: none recorded" in result.output
        assert "No root recorded yet" in result.output
        assert "2 detached" in result.output

    def test_filtered_tree_keeps_the_path_from_the_root(self, tmp_path: Path) -> None:
        result = _invoke(tmp_path, ["list", "--tree", "--blocked"])
        out = result.output

        assert "Notification permission (onboarding)" in out
        assert "(auto) → Sign in (auth)" in out
        assert "LOG IN WITH GOOGLE → Google sign-in consent" in out
        assert "→ Home (main)" not in out
        assert "Listing detail" not in out
        assert "Legacy orphan" not in out
        assert "Screens (ios)" not in out


class TestListJson:
    def test_unfiltered_json_is_the_tree_response_verbatim(self, tmp_path: Path) -> None:
        result = _invoke(tmp_path, ["list"], json_mode=True)

        assert result.exit_code == 0
        assert json.loads(result.output) == FIXTURE

    def test_context_stays_snake_case(self, tmp_path: Path) -> None:
        result = _invoke(tmp_path, ["list"], json_mode=True)

        home = json.loads(result.output)["trees"][0]["screens"][4]
        assert home["screenKey"] == "home"
        assert home["context"]["requires_auth"] is True
        assert home["context"]["deeplink_uri"] == "tinder://home"
        assert "requiresAuth" not in home["context"]

    def test_unknown_fields_are_tolerated(self, tmp_path: Path) -> None:
        payload = copy.deepcopy(FIXTURE)
        payload["trees"][0]["somethingNew"] = 1
        payload["trees"][0]["transitions"][0]["consecutiveFailures"] = 2

        result = _invoke(tmp_path, ["list"], json_mode=True, handler=_serve(payload))

        assert result.exit_code == 0
        assert json.loads(result.output)["trees"][0]["transitions"][0]["id"] == "t01"

    def test_filtered_json_narrows_screens_transitions_and_counts(self, tmp_path: Path) -> None:
        result = _invoke(tmp_path, ["list", "--blocked"], json_mode=True)

        data = json.loads(result.output)
        assert [t["platform"] for t in data["trees"]] == ["android"]
        tree = data["trees"][0]
        assert [s["screenKey"] for s in tree["screens"]] == [
            "google sign-in consent",
            "phone verification",
        ]
        assert tree["counts"] == {
            "explored": 1,
            "pending": 1,
            "blocked": 2,
            "skipped": 0,
            "screens": 2,
        }
        assert sorted(t["id"] for t in tree["transitions"]) == [
            "t03", "t04", "t07", "t08", "t09", "t10",
        ]  # fmt: skip
        assert tree["detachedScreenKeys"] == []
        assert tree["rootScreenKey"] == "notification permission"

    def test_filtered_json_keeps_detached_screens_that_match(self, tmp_path: Path) -> None:
        payload = copy.deepcopy(FIXTURE)
        payload["trees"][0]["screens"][-1]["area"] = "main"

        result = _invoke(
            tmp_path, ["list", "--area", "main"], json_mode=True, handler=_serve(payload)
        )

        tree = json.loads(result.output)["trees"][0]
        assert tree["detachedScreenKeys"] == ["legacy orphan"]
        assert tree["counts"]["screens"] == 3


class TestGetScreen:
    def test_get_renders_identity_context_and_links(self, tmp_path: Path) -> None:
        result = _invoke(tmp_path, ["get", "Sign in", "--platform", "android"])
        out = result.output

        assert result.exit_code == 0
        assert "Sign in  (android)" in out
        assert "Key           : sign in" in out
        assert "Depth         : 1" in out
        assert "Area          : auth" in out
        assert "Notes         : Phone-first auth; Google and Apple SSO sit below the fold." in out
        assert "Screenshot    : https://storage.example/signed/android/sign-in.png" in out
        assert "Reachable via : walk" in out
        assert "Notification permission via (auto) (signed out) (parent)" in out
        assert "Notification permission via Allow (signed out)" in out
        assert "Google sign-in consent via Cancel (signed out)" in out
        assert "Profile via Log out (swiper)" in out
        assert "LOG IN WITH GOOGLE → Google sign-in consent (signed out)" in out
        assert "Skip → Home (signed out)" in out

    def test_get_lists_elements_pending_first_explored_last(self, tmp_path: Path) -> None:
        result = _invoke(tmp_path, ["get", "sign in", "--platform", "android"])
        out = result.output

        pending = _line(out, "Trouble logging in?")
        assert "pending" in pending and "signed out" in pending
        explored = [line for line in out.splitlines() if "│ explored" in line]
        assert out.index(pending) < out.index(explored[0])
        skips = [line for line in explored if "│ Skip " in line]
        assert [("signed out" in s, "swiper" in s, "→ Home" in s) for s in skips] == [
            (True, False, True),
            (False, True, True),
        ]

    def test_get_shows_blocked_and_skipped_reasons_with_account(self, tmp_path: Path) -> None:
        consent = _invoke(tmp_path, ["get", "google sign-in consent"]).output
        blocked = _line(consent, "Choose an account")
        assert "blocked" in blocked
        assert "Google account picker needs a real device account" in blocked
        assert "gated by ask 5b0c9a51-6d8e-4f7a-9d61-2f3c1e0a7b44" in blocked

        listing = _invoke(tmp_path, ["get", "Listing detail"]).output
        skipped = _line(listing, "Book now")
        assert "skipped" in skipped and "payment" in skipped and "swiper" in skipped
        assert "Home via Listing card (swiper) (parent)" in listing
        assert "None — no screen is placed under this one." in listing

    def test_get_root_and_detached_screens(self, tmp_path: Path) -> None:
        root = _invoke(tmp_path, ["get", "Notification permission"]).output
        assert "Nothing — this is the root." in root
        assert "Cheap to reach: no — needs a fresh install to show again" in root

        orphan = _invoke(tmp_path, ["get", "legacy orphan"]).output
        assert "Depth         : — (detached: not reachable from the root)" in orphan
        assert "Nothing — no explored transition leads here." in orphan
        assert "No context recorded for this screen." in orphan

    def test_get_reports_every_platform_match(self, tmp_path: Path) -> None:
        result = _invoke(tmp_path, ["get", "SIGN IN"])

        assert result.exit_code == 0
        assert "2 screens match 'SIGN IN' (android, ios). Use --platform to narrow." in (
            result.output
        )
        assert "Sign in  (android)" in result.output
        assert "Sign in  (ios)" in result.output

    def test_get_unknown_screen_exits_4(self, tmp_path: Path) -> None:
        result = _invoke(tmp_path, ["get", "checkout"])

        assert result.exit_code == 4
        assert "No mapped screen matches 'checkout'" in result.output

    def test_get_json_narrows_each_tree_to_the_screen(self, tmp_path: Path) -> None:
        result = _invoke(tmp_path, ["get", "home"], json_mode=True)

        data = json.loads(result.output)
        assert data["appId"] == FIXTURE["appId"]
        [tree] = data["trees"]
        assert [s["screenKey"] for s in tree["screens"]] == ["home"]
        assert sorted(t["id"] for t in tree["transitions"]) == [
            "t05", "t11", "t12", "t13", "t15", "t19",
        ]  # fmt: skip
        assert tree["counts"] == {
            "explored": 2,
            "pending": 1,
            "blocked": 0,
            "skipped": 0,
            "screens": 1,
        }

    def test_get_json_with_two_platform_matches_keeps_both_trees(self, tmp_path: Path) -> None:
        result = _invoke(tmp_path, ["get", "sign in"], json_mode=True)

        trees = json.loads(result.output)["trees"]
        assert [(t["platform"], [s["screenKey"] for s in t["screens"]]) for t in trees] == [
            ("android", ["sign in"]),
            ("ios", ["sign in"]),
        ]
