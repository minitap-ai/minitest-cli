"""Tests for the `minitest init` command."""

import json
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from minitest_cli.commands.init import _AGENT_ENV_VARS, _is_agent_context
from minitest_cli.commands.init_playbook import PLAYBOOK
from minitest_cli.main import app

runner = CliRunner()

_HUMAN_MARKER = "writes the onboarding plan"


@pytest.fixture(autouse=True)
def _no_update_check():
    with patch("minitest_cli.main.check_for_updates", return_value=None):
        yield


@pytest.fixture(autouse=True)
def _clear_agent_env(monkeypatch):
    for var in _AGENT_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


class TestAgentContextDetection:
    """`_is_agent_context` decides raw-vs-rendered output."""

    def test_agent_flag_wins_even_on_tty(self):
        with patch("minitest_cli.commands.init.sys.stdout.isatty", return_value=True):
            assert _is_agent_context(agent_flag=True, json_mode=False) is True

    def test_json_mode_wins_even_on_tty(self):
        with patch("minitest_cli.commands.init.sys.stdout.isatty", return_value=True):
            assert _is_agent_context(agent_flag=False, json_mode=True) is True

    def test_agent_env_var_wins_on_tty(self, monkeypatch):
        monkeypatch.setenv("CLAUDECODE", "1")
        with patch("minitest_cli.commands.init.sys.stdout.isatty", return_value=True):
            assert _is_agent_context(agent_flag=False, json_mode=False) is True

    def test_interactive_tty_is_human(self):
        with patch("minitest_cli.commands.init.sys.stdout.isatty", return_value=True):
            assert _is_agent_context(agent_flag=False, json_mode=False) is False

    def test_piped_stdout_is_agent(self):
        with patch("minitest_cli.commands.init.sys.stdout.isatty", return_value=False):
            assert _is_agent_context(agent_flag=False, json_mode=False) is True


class TestInitRendering:
    """`minitest init` emits the playbook in the right shape per context."""

    def test_agent_context_prints_raw_playbook_only(self):
        with patch("minitest_cli.commands.init._is_agent_context", return_value=True):
            result = runner.invoke(app, ["init"])

        assert result.exit_code == 0
        assert result.stdout == PLAYBOOK

    def test_human_context_adds_intro_around_playbook(self):
        with patch("minitest_cli.commands.init._is_agent_context", return_value=False):
            result = runner.invoke(app, ["init"])

        assert result.exit_code == 0
        assert _HUMAN_MARKER in result.output
        assert "Minitest onboarding" in result.output
        assert result.output != PLAYBOOK

    def test_json_mode_emits_playbook_as_json(self):
        result = runner.invoke(app, ["--json", "init"])

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["playbook"] == PLAYBOOK


class TestPlaybookContent:
    """The playbook must cover the full onboarding flow end-to-end."""

    def test_covers_every_onboarding_stage(self):
        for command in (
            "minitest auth login",
            "minitest apps list",
            "minitest apps create",
            "minitest test-profile create",
            "minitest flow-types list",
            "minitest user-story create",
            "minitest apps dependencies",
            "minitest build upload",
            "minitest run all",
        ):
            assert command in PLAYBOOK

    def test_wires_dependencies_and_personas(self):
        assert "--depends-on" in PLAYBOOK
        assert "--profile" in PLAYBOOK
        assert "--password-stdin" in PLAYBOOK

    def test_covers_file_seeding(self):
        assert "minitest test-file upload" in PLAYBOOK
        assert "minitest user-story-binding set-files" in PLAYBOOK

    def test_offline_wording_avoids_airplane_mode(self):
        assert "Offline (wifi off)" in PLAYBOOK
        assert 'never write "airplane mode"' in PLAYBOOK
