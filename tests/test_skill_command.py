"""Tests for the skill command."""

from unittest.mock import MagicMock, patch

import httpx
from typer.testing import CliRunner

from minitest_cli import __version__
from minitest_cli.main import app

runner = CliRunner()


def _mock_response(status_code: int, text: str) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = text
    return resp


class TestSkillCommand:
    """`minitest skill` prints the skill bundled with this CLI version."""

    def test_prints_bundled_skill_without_network(self) -> None:
        with (
            patch("minitest_cli.main.check_for_updates", return_value=None),
            patch("minitest_cli.commands.skill.httpx.get") as mock,
        ):
            result = runner.invoke(app, ["skill"])

        assert result.exit_code == 0
        assert result.output.startswith("---\nname: minitest-cli\n")
        assert f'cli-version: "{__version__}"' in result.output
        mock.assert_not_called()

    def test_override_url_is_fetched(self, monkeypatch) -> None:
        monkeypatch.setenv("MINITEST_SKILL_URL", "https://example.test/SKILL.md")
        resp = _mock_response(200, "# Fork skill")

        with (
            patch("minitest_cli.main.check_for_updates", return_value=None),
            patch("minitest_cli.commands.skill.httpx.get", return_value=resp) as mock,
        ):
            result = runner.invoke(app, ["skill"])

        assert result.exit_code == 0
        assert "# Fork skill" in result.output
        mock.assert_called_once_with(
            "https://example.test/SKILL.md", timeout=15, follow_redirects=True
        )

    def test_override_network_error(self, monkeypatch) -> None:
        monkeypatch.setenv("MINITEST_SKILL_URL", "https://example.test/SKILL.md")
        with patch(
            "minitest_cli.commands.skill.httpx.get",
            side_effect=httpx.ConnectError("Connection refused"),
        ):
            result = runner.invoke(app, ["skill"])

        assert result.exit_code == 3
        assert "Network error" in result.output

    def test_override_non_200(self, monkeypatch) -> None:
        monkeypatch.setenv("MINITEST_SKILL_URL", "https://example.test/SKILL.md")
        resp = _mock_response(404, "Not Found")

        with patch("minitest_cli.commands.skill.httpx.get", return_value=resp):
            result = runner.invoke(app, ["skill"])

        assert result.exit_code == 3
        assert "HTTP 404" in result.output
