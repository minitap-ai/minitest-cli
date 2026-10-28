"""Tests for the upgrade command."""

from unittest.mock import MagicMock, patch

import httpx
from typer.testing import CliRunner

from minitest_cli.main import app

runner = CliRunner()


def _mock_response(status_code: int, text: str = "", json_data: dict | None = None) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = text
    if json_data is not None:
        resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


def _patch_update_check():
    return patch("minitest_cli.main.check_for_updates", return_value=None)


class TestUpgradeCLI:
    """Tests for CLI self-update logic."""

    def test_cli_already_up_to_date(self) -> None:
        """When PyPI version matches current, report up to date."""
        pypi_resp = _mock_response(200, json_data={"info": {"version": "0.5.1"}})

        with (
            _patch_update_check(),
            patch("minitest_cli.commands.upgrade.httpx.get", return_value=pypi_resp),
            patch("minitest_cli.commands.upgrade.__version__", "0.5.1"),
            patch("minitest_cli.utils.skill_refresh.find_skill_paths", return_value=[]),
        ):
            result = runner.invoke(app, ["upgrade"])

        assert result.exit_code == 0
        assert "already up to date" in result.output

    def test_cli_upgrade_uv(self) -> None:
        """When a newer version exists, upgrade with uv."""
        pypi_resp = _mock_response(200, json_data={"info": {"version": "0.6.0"}})

        with (
            _patch_update_check(),
            patch("minitest_cli.commands.upgrade.httpx.get", return_value=pypi_resp),
            patch("minitest_cli.commands.upgrade.__version__", "0.5.1"),
            patch("minitest_cli.commands.upgrade.shutil.which", return_value="/usr/local/bin/uv"),
            patch("minitest_cli.commands.upgrade.subprocess.run") as mock_run,
            patch("minitest_cli.utils.skill_refresh.find_skill_paths", return_value=[]),
        ):
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = runner.invoke(app, ["upgrade"])

        assert result.exit_code == 0
        first_call_args = mock_run.call_args_list[0]
        cmd = first_call_args[0][0]
        assert cmd == ["/usr/local/bin/uv", "tool", "upgrade", "--reinstall", "minitest-cli"]

    def test_cli_upgrade_falls_back_to_python_uv(self) -> None:
        """Without uv on PATH, run uv as a module (Homebrew is no longer used)."""
        pypi_resp = _mock_response(200, json_data={"info": {"version": "0.6.0"}})

        with (
            _patch_update_check(),
            patch("minitest_cli.commands.upgrade.httpx.get", return_value=pypi_resp),
            patch("minitest_cli.commands.upgrade.__version__", "0.5.1"),
            patch("minitest_cli.commands.upgrade.shutil.which", return_value=None),
            patch("minitest_cli.commands.upgrade.subprocess.run") as mock_run,
            patch("minitest_cli.utils.skill_refresh.find_skill_paths", return_value=[]),
        ):
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = runner.invoke(app, ["upgrade"])

        assert result.exit_code == 0
        cmd = mock_run.call_args_list[0][0][0]
        assert cmd[1:] == ["-m", "uv", "tool", "upgrade", "--reinstall", "minitest-cli"]

    def test_cli_nothing_to_upgrade(self) -> None:
        """When upgrade tool reports 'Nothing to upgrade', treat as failure."""
        pypi_resp = _mock_response(200, json_data={"info": {"version": "0.6.0"}})

        with (
            _patch_update_check(),
            patch("minitest_cli.commands.upgrade.httpx.get", return_value=pypi_resp),
            patch("minitest_cli.commands.upgrade.__version__", "0.5.1"),
            patch("minitest_cli.commands.upgrade.shutil.which", return_value="/usr/local/bin/uv"),
            patch("minitest_cli.commands.upgrade.subprocess.run") as mock_run,
            patch("minitest_cli.utils.skill_refresh.find_skill_paths", return_value=[]),
        ):
            mock_run.return_value = MagicMock(
                returncode=0, stdout="Nothing to upgrade\n", stderr=""
            )
            result = runner.invoke(app, ["upgrade"])

        assert "nothing to upgrade" in result.output.lower()
        assert "manually" in result.output.lower()

    def test_cli_pypi_unreachable(self) -> None:
        """When PyPI is unreachable, show error."""
        with (
            _patch_update_check(),
            patch(
                "minitest_cli.commands.upgrade.httpx.get",
                side_effect=httpx.ConnectError("Connection refused"),
            ),
            patch("minitest_cli.utils.skill_refresh.find_skill_paths", return_value=[]),
        ):
            result = runner.invoke(app, ["upgrade"])

        assert "Could not check PyPI" in result.output


class TestUpgradeSkill:
    """Tests for skill refresh logic."""

    def test_skill_not_installed(self) -> None:
        """When skill is not installed, report and suggest install command."""
        pypi_resp = _mock_response(200, json_data={"info": {"version": "0.5.1"}})

        with (
            _patch_update_check(),
            patch("minitest_cli.commands.upgrade.httpx.get", return_value=pypi_resp),
            patch("minitest_cli.commands.upgrade.__version__", "0.5.1"),
            patch("minitest_cli.utils.skill_refresh.find_skill_paths", return_value=[]),
        ):
            result = runner.invoke(app, ["upgrade"])

        assert "not installed" in result.output

    def test_skill_up_to_date(self, tmp_path) -> None:
        """An installed skill identical to the bundled one is reported up to date."""
        from minitest_cli.utils import skill_bundle

        skill_dir = tmp_path / "minitest-cli"
        skill_bundle.install_into(skill_dir)

        pypi_resp = _mock_response(200, json_data={"info": {"version": "0.5.1"}})

        with (
            _patch_update_check(),
            patch("minitest_cli.commands.upgrade.httpx.get", return_value=pypi_resp),
            patch("minitest_cli.commands.upgrade.__version__", "0.5.1"),
            patch(
                "minitest_cli.utils.skill_refresh.find_skill_paths",
                return_value=[str(skill_dir)],
            ),
        ):
            result = runner.invoke(app, ["upgrade"])

        assert "skill is already up to date" in result.output.lower()

    def test_skill_outdated(self, tmp_path) -> None:
        """An installed skill that differs from the bundled one is refreshed in place."""
        skill_dir = tmp_path / "minitest-cli"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("old content")

        pypi_resp = _mock_response(200, json_data={"info": {"version": "0.5.1"}})

        with (
            _patch_update_check(),
            patch("minitest_cli.commands.upgrade.httpx.get", return_value=pypi_resp),
            patch("minitest_cli.commands.upgrade.__version__", "0.5.1"),
            patch(
                "minitest_cli.utils.skill_refresh.find_skill_paths",
                return_value=[str(skill_dir)],
            ),
        ):
            result = runner.invoke(app, ["upgrade"])

        assert "updated" in result.output.lower()
        assert (skill_dir / "SKILL.md").read_text() != "old content"
        assert (skill_dir / "reference").is_dir()


class TestUpgradeStatus:
    """Tests for the 'everything up to date' banner logic."""

    def test_shows_banner_when_both_up_to_date(self, tmp_path) -> None:
        """Banner shown when CLI and skill are both already current."""
        from minitest_cli.utils import skill_bundle

        skill_dir = tmp_path / "minitest-cli"
        skill_bundle.install_into(skill_dir)

        pypi_resp = _mock_response(200, json_data={"info": {"version": "0.5.1"}})

        with (
            _patch_update_check(),
            patch("minitest_cli.commands.upgrade.httpx.get", return_value=pypi_resp),
            patch("minitest_cli.commands.upgrade.__version__", "0.5.1"),
            patch(
                "minitest_cli.utils.skill_refresh.find_skill_paths",
                return_value=[str(skill_dir)],
            ),
        ):
            result = runner.invoke(app, ["upgrade"])

        assert "Everything is up to date" in result.output

    def test_no_banner_after_cli_failure(self) -> None:
        """Banner NOT shown when PyPI check fails."""
        with (
            _patch_update_check(),
            patch(
                "minitest_cli.commands.upgrade.httpx.get",
                side_effect=httpx.ConnectError("Connection refused"),
            ),
            patch("minitest_cli.utils.skill_refresh.find_skill_paths", return_value=[]),
        ):
            result = runner.invoke(app, ["upgrade"])

        assert "Everything is up to date" not in result.output
