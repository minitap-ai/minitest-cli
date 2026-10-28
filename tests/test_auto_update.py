"""Tests for the background auto-update: where it runs, what it decides, how it starts."""

import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from minitest_cli.core.config import Settings
from minitest_cli.utils import auto_update
from minitest_cli.utils.auto_update import InstallMethod, Plan
from minitest_cli.utils.auto_update_state import read_state, section, update_section

NOW = 1_800_000_000.0
SETTLED = NOW - 2 * 3600
FRESH = NOW - 10 * 60


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(config_dir=tmp_path)


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """An environment where auto-update is allowed."""
    for name in ("MINITEST_NO_AUTO_UPDATE", "CI", "KUBERNETES_SERVICE_HOST"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(auto_update, "DOCKERENV_PATH", tmp_path / "no-dockerenv")
    monkeypatch.setattr(sys, "platform", "darwin")


@pytest.fixture
def uv_install(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    prefix = tmp_path / "uv-tools" / "minitest-cli"
    prefix.mkdir(parents=True)
    (prefix / "uv-receipt.toml").write_text("[tool]\n")
    monkeypatch.setattr(sys, "prefix", str(prefix))
    monkeypatch.setattr(auto_update, "_find_binary", lambda name, _fallbacks: f"/bin/{name}")


class TestEnvironmentBlocker:
    def test_blocker_none_in_clean_environment(self, clean_env: None) -> None:
        assert auto_update.environment_blocker() is None

    @pytest.mark.parametrize(
        ("name", "value"),
        [("MINITEST_NO_AUTO_UPDATE", "1"), ("CI", "true"), ("KUBERNETES_SERVICE_HOST", "10.0.0.1")],
    )
    def test_blocker_set_by_environment(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch, name: str, value: str
    ) -> None:
        monkeypatch.setenv(name, value)
        assert auto_update.environment_blocker() is not None

    def test_blocker_ignores_falsy_values(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CI", "false")
        monkeypatch.setenv("MINITEST_NO_AUTO_UPDATE", "0")
        assert auto_update.environment_blocker() is None

    def test_blocker_set_in_docker(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        dockerenv = tmp_path / ".dockerenv"
        dockerenv.touch()
        monkeypatch.setattr(auto_update, "DOCKERENV_PATH", dockerenv)
        assert auto_update.environment_blocker() == "running in a container"

    def test_blocker_set_on_windows(self, clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "platform", "win32")
        assert auto_update.environment_blocker() is not None


class TestInstallMethod:
    def test_install_method_uv_tool(self, uv_install: None) -> None:
        assert auto_update.install_method() is InstallMethod.UV

    def test_install_method_homebrew(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "prefix", "/opt/homebrew/Cellar/minitest-cli/0.41.0/libexec")
        assert auto_update.install_method() is InstallMethod.BREW

    def test_install_method_unknown_for_dev_checkout(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(sys, "prefix", str(tmp_path / ".venv"))
        assert auto_update.install_method() is None

    def test_upgrade_command_uses_uv_tool_upgrade(self, uv_install: None) -> None:
        assert auto_update.upgrade_command(InstallMethod.UV) == [
            "/bin/uv",
            "tool",
            "upgrade",
            "minitest-cli",
        ]

    def test_upgrade_command_none_without_binary(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(auto_update, "_find_binary", lambda _name, _fallbacks: None)
        assert auto_update.upgrade_command(InstallMethod.BREW) is None


class TestPlan:
    @pytest.fixture(autouse=True)
    def _old_version(self, monkeypatch: pytest.MonkeyPatch, uv_install: None) -> None:
        monkeypatch.setattr(auto_update, "__version__", "0.41.0")

    def test_plan_upgrades_settled_release(self, settings: Settings) -> None:
        todo = auto_update.plan(settings, "0.42.0", SETTLED, NOW)
        assert todo == Plan(cli_target="0.42.0", method=InstallMethod.UV, skill=True)

    def test_plan_waits_for_fresh_release(self, settings: Settings) -> None:
        assert auto_update.plan(settings, "0.42.0", FRESH, NOW).cli_target is None

    def test_plan_waits_when_release_time_unknown(self, settings: Settings) -> None:
        assert auto_update.plan(settings, "0.42.0", None, NOW).cli_target is None

    def test_plan_skips_current_version(self, settings: Settings) -> None:
        assert auto_update.plan(settings, "0.41.0", SETTLED, NOW).cli_target is None

    def test_plan_does_not_retry_within_a_day(self, settings: Settings) -> None:
        update_section(settings, "cli", target="0.42.0", status="failed", startedAt=NOW - 3600)
        assert auto_update.plan(settings, "0.42.0", SETTLED, NOW).cli_target is None

    def test_plan_retries_after_a_day(self, settings: Settings) -> None:
        update_section(settings, "cli", target="0.42.0", status="failed", startedAt=NOW - 90000)
        assert auto_update.plan(settings, "0.42.0", SETTLED, NOW).cli_target == "0.42.0"

    def test_plan_retries_deferred_update(self, settings: Settings) -> None:
        update_section(settings, "cli", target="0.42.0", status="deferred", startedAt=NOW - 60)
        assert auto_update.plan(settings, "0.42.0", SETTLED, NOW).cli_target == "0.42.0"

    def test_plan_skips_upgrade_for_dev_checkout(
        self, settings: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(sys, "prefix", str(tmp_path / ".venv"))
        todo = auto_update.plan(settings, "0.42.0", SETTLED, NOW)
        assert todo.cli_target is None
        assert todo.skill is True

    def test_plan_skill_not_due_after_recent_check(self, settings: Settings) -> None:
        update_section(settings, "skill", checkedAt=NOW - 60)
        assert auto_update.plan(settings, "0.41.0", SETTLED, NOW).skill is False


class TestStart:
    def test_start_spawns_detached_worker(self, settings: Settings) -> None:
        worker = MagicMock(pid=os.getpid())
        todo = Plan(cli_target="0.42.0", method=InstallMethod.UV, skill=True)
        with patch("minitest_cli.utils.auto_update.subprocess.Popen", return_value=worker) as popen:
            assert auto_update.start(settings, todo, NOW) is True

        args = popen.call_args.args[0]
        assert args[1:] == [
            "-m",
            auto_update.WORKER_MODULE,
            "--cli-target",
            "0.42.0",
            "--method",
            "uv",
            "--skill",
        ]
        assert popen.call_args.kwargs["start_new_session"] is True
        assert popen.call_args.kwargs["stdin"] is not None
        state = read_state(settings)
        assert section(state, "cli")["status"] == "running"
        assert section(state, "skill")["checkedAt"] == NOW
        assert (settings.config_dir / "auto_update.lock").read_text() == str(os.getpid())

    def test_start_refuses_while_another_update_runs(self, settings: Settings) -> None:
        todo = Plan(cli_target=None, method=None, skill=True)
        with patch(
            "minitest_cli.utils.auto_update.subprocess.Popen",
            return_value=MagicMock(pid=os.getpid()),
        ) as popen:
            assert auto_update.start(settings, todo, NOW) is True
            assert auto_update.start(settings, todo, NOW) is False
        assert popen.call_count == 1

    def test_start_nothing_to_do(self, settings: Settings) -> None:
        with patch("minitest_cli.utils.auto_update.subprocess.Popen") as popen:
            assert auto_update.start(settings, Plan(None, None, False), NOW) is False
        popen.assert_not_called()

    def test_start_failure_releases_lock(self, settings: Settings) -> None:
        todo = Plan(cli_target="0.42.0", method=InstallMethod.UV, skill=False)
        with patch("minitest_cli.utils.auto_update.subprocess.Popen", side_effect=OSError):
            assert auto_update.start(settings, todo, time.time()) is False
        assert not (settings.config_dir / "auto_update.lock").exists()
        assert section(read_state(settings), "cli")["status"] == "failed"
