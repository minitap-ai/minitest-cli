"""Tests for `minitest upgrade auto [on|off]` and the saved auto-update preference."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from minitest_cli.core.config import Settings
from minitest_cli.main import app
from minitest_cli.utils import auto_update
from minitest_cli.utils.auto_update_state import auto_update_enabled, update_section

runner = CliRunner()


@pytest.fixture
def config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("MINITEST_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("MINITEST_NO_AUTO_UPDATE", raising=False)
    monkeypatch.setattr(auto_update, "environment_blocker", lambda: None)
    return tmp_path


def _invoke(*args: str):
    with patch("minitest_cli.main.check_for_updates"):
        return runner.invoke(app, list(args))


class TestAutoUpdatePreference:
    def test_preference_defaults_to_on(self, tmp_path: Path) -> None:
        assert auto_update_enabled(Settings(config_dir=tmp_path)) is True

    def test_saved_off_blocks_auto_update(self, config_dir: Path) -> None:
        result = _invoke("upgrade", "auto", "off")
        assert result.exit_code == 0, result.output
        settings = Settings(config_dir=config_dir)
        assert auto_update_enabled(settings) is False
        assert auto_update.blocker(settings) == "turned off with `minitest upgrade auto off`"

    def test_turn_back_on(self, config_dir: Path) -> None:
        _invoke("upgrade", "auto", "off")
        result = _invoke("upgrade", "auto", "on")
        assert result.exit_code == 0, result.output
        assert auto_update.blocker(Settings(config_dir=config_dir)) is None
        assert json.loads((config_dir / "preferences.json").read_text()) == {"autoUpdate": True}

    def test_environment_opt_out_wins_over_saved_on(
        self, config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _invoke("upgrade", "auto", "on")
        monkeypatch.setattr(auto_update, "environment_blocker", lambda: "running in CI")
        assert auto_update.blocker(Settings(config_dir=config_dir)) == "running in CI"


class TestUpgradeAutoCommand:
    def test_status_json(self, config_dir: Path) -> None:
        update_section(Settings(config_dir=config_dir), "cli", target="0.42.0", status="done")
        result = _invoke("--json", "upgrade", "auto")
        assert result.exit_code == 0, result.output
        status = json.loads(result.stdout)
        assert status["autoUpdate"] == "on"
        assert status["reason"] is None
        assert status["lastUpdate"] == {"target": "0.42.0", "status": "done"}
        assert status["log"].endswith("auto_update.log")

    def test_status_human_after_off(self, config_dir: Path) -> None:
        result = _invoke("upgrade", "auto", "off")
        assert "Auto-update: off" in result.stdout
        assert "upgrade auto off" in result.stdout

    def test_status_warns_when_install_cannot_update(self, config_dir: Path) -> None:
        with patch.object(auto_update, "cli_upgrade_supported", return_value=False):
            result = _invoke("upgrade", "auto")
        assert "cannot update itself" in result.stdout

    def test_rejects_unknown_switch(self, config_dir: Path) -> None:
        assert _invoke("upgrade", "auto", "maybe").exit_code == 2

    def test_upgrade_without_subcommand_still_upgrades(self, config_dir: Path) -> None:
        with (
            patch("minitest_cli.commands.upgrade._upgrade_cli") as upgrade_cli,
            patch("minitest_cli.commands.upgrade.check_and_refresh", return_value="skipped"),
        ):
            result = _invoke("upgrade")
        assert result.exit_code == 0, result.output
        upgrade_cli.assert_called_once()
