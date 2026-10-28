"""Tests for the auto-update worker, its lock/registry, notices, and the per-command hook."""

import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from minitest_cli.core.config import Settings
from minitest_cli.utils import auto_update, auto_update_notices, auto_update_worker, update_check
from minitest_cli.utils.auto_update import Plan
from minitest_cli.utils.auto_update_state import (
    acquire_lock,
    hand_lock_to,
    other_commands_running,
    read_state,
    section,
    update_section,
)
from minitest_cli.utils.skill_refresh import UpgradeStatus

DEAD_PID = 2**22 - 1


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(config_dir=tmp_path)


@pytest.fixture
def worker_settings(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setattr(auto_update_worker, "get_settings", lambda: settings)
    monkeypatch.setattr(auto_update_worker, "IDLE_POLL_SECONDS", 0.01)
    return settings


class TestLockAndRegistry:
    def test_lock_is_exclusive(self, settings: Settings) -> None:
        assert acquire_lock(settings) is True
        assert acquire_lock(settings) is False

    def test_lock_held_by_dead_process_is_taken_over(self, settings: Settings) -> None:
        assert acquire_lock(settings) is True
        hand_lock_to(settings, DEAD_PID)
        assert acquire_lock(settings) is True

    def test_running_marker_of_live_process_counts(self, settings: Settings) -> None:
        (settings.config_dir / "running").mkdir()
        (settings.config_dir / "running" / str(os.getppid())).touch()
        assert other_commands_running(settings) is True

    def test_dead_running_marker_is_pruned(self, settings: Settings) -> None:
        marker = settings.config_dir / "running" / str(DEAD_PID)
        marker.parent.mkdir()
        marker.touch()
        assert other_commands_running(settings) is False
        assert not marker.exists()


class TestWorker:
    def test_worker_upgrades_and_refreshes_skill(
        self, worker_settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            auto_update_worker, "upgrade_command", lambda: [sys.executable, "-c", "print(1)"]
        )
        monkeypatch.setattr(auto_update_worker, "fetch_latest_release", lambda: ("0.42.0", 0.0))
        skill_versions = iter(["old", "new"])
        monkeypatch.setattr(
            auto_update_worker, "_local_skill_content", lambda: next(skill_versions)
        )
        acquire_lock(worker_settings)
        with patch.object(
            auto_update_worker, "check_and_refresh", return_value=UpgradeStatus.UPGRADED
        ):
            assert auto_update_worker.run(["--cli-target", "0.42.0", "--skill"]) == 0

        state = read_state(worker_settings)
        assert section(state, "cli")["status"] == "done"
        assert section(state, "skill")["status"] == "upgraded"
        assert not (worker_settings.config_dir / "auto_update.lock").exists()

    def test_worker_does_not_claim_refresh_when_skill_unchanged(
        self, worker_settings: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("same")
        monkeypatch.setattr(auto_update_worker, "find_skill_path", lambda: str(skill_dir))
        with patch.object(
            auto_update_worker, "check_and_refresh", return_value=UpgradeStatus.UPGRADED
        ):
            auto_update_worker.run(["--skill"])
        assert section(read_state(worker_settings), "skill")["status"] == "up_to_date"

    def test_worker_records_failed_upgrade(
        self, worker_settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            auto_update_worker, "upgrade_command", lambda: [sys.executable, "-c", "exit(2)"]
        )
        monkeypatch.setattr(auto_update_worker, "fetch_latest_release", lambda: ("0.42.0", 0.0))
        auto_update_worker.run(["--cli-target", "0.42.0"])
        assert section(read_state(worker_settings), "cli")["status"] == "failed"

    def test_worker_defers_when_newer_release_is_too_fresh(
        self, worker_settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            auto_update_worker, "fetch_latest_release", lambda: ("0.43.0", time.time())
        )
        with patch.object(auto_update_worker.subprocess, "run") as run:
            auto_update_worker.run(["--cli-target", "0.42.0"])
        run.assert_not_called()
        assert section(read_state(worker_settings), "cli")["status"] == "deferred"

    def test_worker_defers_while_commands_keep_running(
        self, worker_settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(auto_update_worker, "IDLE_TIMEOUT_SECONDS", 0)
        monkeypatch.setattr(auto_update_worker, "other_commands_running", lambda _s: True)
        update_section(worker_settings, "skill", checkedAt=123.0)
        with patch.object(auto_update_worker.subprocess, "run") as run:
            auto_update_worker.run(["--cli-target", "0.42.0", "--skill"])
        run.assert_not_called()
        state = read_state(worker_settings)
        assert section(state, "cli")["status"] == "deferred"
        assert section(state, "skill")["checkedAt"] == 0

    def test_worker_module_runs_as_script(self, settings: Settings) -> None:
        result = subprocess.run(
            [sys.executable, "-m", auto_update.WORKER_MODULE, "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0
        assert "--cli-target" in result.stdout


class TestNotices:
    def test_notice_after_successful_update_shown_once(
        self, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(auto_update_notices, "__version__", "0.42.0")
        update_section(settings, "cli", target="0.42.0", status="done", notified=False)
        assert auto_update_notices.pending_notices(settings) == [
            "minitest-cli updated itself to 0.42.0."
        ]
        assert auto_update_notices.pending_notices(settings) == []

    def test_notice_when_version_did_not_move(
        self, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(auto_update_notices, "__version__", "0.41.0")
        update_section(settings, "cli", target="0.42.0", status="done", notified=False)
        [notice] = auto_update_notices.pending_notices(settings)
        assert "could not update itself to 0.42.0" in notice

    def test_no_notice_while_update_runs(self, settings: Settings) -> None:
        update_section(settings, "cli", target="0.42.0", status="running", notified=False)
        assert auto_update_notices.pending_notices(settings) == []

    def test_notice_after_skill_refresh(self, settings: Settings) -> None:
        update_section(settings, "skill", status="upgraded", notified=False)
        [notice] = auto_update_notices.pending_notices(settings)
        assert "agent skill was refreshed" in notice


class TestCheckForUpdates:
    @pytest.fixture(autouse=True)
    def _env(self, monkeypatch: pytest.MonkeyPatch, settings: Settings) -> None:
        monkeypatch.delenv("MINITEST_NO_AUTO_UPDATE", raising=False)
        monkeypatch.setattr(auto_update, "environment_blocker", lambda: None)
        monkeypatch.setattr(update_check, "register_running", lambda _s: None)
        monkeypatch.setattr(update_check, "__version__", "0.41.0")
        monkeypatch.setattr(update_check, "_latest_release", lambda _s: ("0.42.0", 0.0))

    def test_starts_background_update_without_panel(
        self, settings: Settings, capsys: pytest.CaptureFixture[str]
    ) -> None:
        todo = Plan(cli_target="0.42.0", skill=True)
        with (
            patch.object(auto_update, "plan", return_value=todo),
            patch.object(auto_update, "start", return_value=True) as start,
            patch.object(auto_update, "cli_upgrade_supported", return_value=True),
        ):
            update_check.check_for_updates(settings)
        start.assert_called_once()
        err = capsys.readouterr().err
        assert "in the background" in err
        assert "out of date" not in err

    def test_shows_panel_when_cli_cannot_update_itself(
        self, settings: Settings, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with (
            patch.object(auto_update, "start", return_value=False),
            patch.object(auto_update, "cli_upgrade_supported", return_value=False),
        ):
            update_check.check_for_updates(settings)
        assert "minitest upgrade" in capsys.readouterr().err

    def test_upgrade_command_never_auto_updates(
        self, settings: Settings, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with patch.object(auto_update, "start") as start:
            update_check.check_for_updates(settings, allow_auto_update=False)
        start.assert_not_called()
        assert "minitest upgrade" in capsys.readouterr().err
