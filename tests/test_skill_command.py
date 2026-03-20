"""Tests for the skill command."""

from unittest.mock import MagicMock, patch

import httpx
from typer.testing import CliRunner

from minitest_cli.commands.skill import SKILL_URL
from minitest_cli.main import app

runner = CliRunner()


def _mock_response(status_code: int, text: str) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = text
    return resp


class TestSkillCommand:
    """Tests for `minitest skill`."""

    def test_fetch_success(self) -> None:
        content = "# Minitest Skill\n\nSome instructions."
        resp = _mock_response(200, content)

        with (
            patch("minitest_cli.main.check_for_updates", return_value=None),
            patch("minitest_cli.commands.skill.httpx.get", return_value=resp) as mock,
        ):
            result = runner.invoke(app, ["skill"])

        assert result.exit_code == 0
        assert content in result.output
        mock.assert_called_once_with(SKILL_URL, timeout=15, follow_redirects=True)

    def test_fetch_http_error(self) -> None:
        with patch(
            "minitest_cli.commands.skill.httpx.get",
            side_effect=httpx.ConnectError("Connection refused"),
        ):
            result = runner.invoke(app, ["skill"])

        assert result.exit_code == 3
        assert "Network error" in result.output

    def test_fetch_timeout(self) -> None:
        with patch(
            "minitest_cli.commands.skill.httpx.get",
            side_effect=httpx.ReadTimeout("Timed out"),
        ):
            result = runner.invoke(app, ["skill"])

        assert result.exit_code == 3
        assert "Network error" in result.output

    def test_fetch_non_200(self) -> None:
        resp = _mock_response(404, "Not Found")

        with patch("minitest_cli.commands.skill.httpx.get", return_value=resp):
            result = runner.invoke(app, ["skill"])

        assert result.exit_code == 3
        assert "HTTP 404" in result.output

    def test_fetch_server_error(self) -> None:
        resp = _mock_response(500, "Internal Server Error")

        with patch("minitest_cli.commands.skill.httpx.get", return_value=resp):
            result = runner.invoke(app, ["skill"])

        assert result.exit_code == 3
        assert "HTTP 500" in result.output

    def test_skill_url_points_to_raw_github(self) -> None:
        assert "raw.githubusercontent.com" in SKILL_URL
        assert "minitap-ai/minitest-cli" in SKILL_URL
        assert "SKILL.md" in SKILL_URL
