"""Tests for the `minitest init` command."""

import json
from unittest.mock import patch

import httpx
import pytest
from typer.testing import CliRunner

from minitest_cli.commands.init import _AGENT_ENV_VARS, _is_agent_context
from minitest_cli.commands.init_helpers import PLAYBOOK_PATH, load_playbook
from minitest_cli.commands.init_playbook import FALLBACK_PLAYBOOK
from minitest_cli.core.config import Settings
from minitest_cli.main import app

runner = CliRunner()

_HUMAN_MARKER = "writes the onboarding plan"
_SERVED = "# Served onboarding\n\nFollow the methodology.\n"


@pytest.fixture(autouse=True)
def _no_update_check():
    with patch("minitest_cli.main.check_for_updates", return_value=None):
        yield


@pytest.fixture(autouse=True)
def _clear_agent_env(monkeypatch):
    for var in _AGENT_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def _served_playbook():
    with patch(
        "minitest_cli.commands.init.load_playbook",
        return_value=(_SERVED, "server"),
    ):
        yield


class _FakeApiClient:
    def __init__(self, response: httpx.Response | Exception) -> None:
        self._response = response
        self.requested_path: str | None = None

    def __call__(self, *_args, **_kwargs) -> "_FakeApiClient":
        return self

    async def __aenter__(self) -> "_FakeApiClient":
        return self

    async def __aexit__(self, *_args) -> None:
        return None

    async def get(self, path: str) -> httpx.Response:
        self.requested_path = path
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


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


class TestPlaybookRetrieval:
    """The served playbook wins; any failure degrades to the embedded copy."""

    def test_served_playbook_is_used(self):
        client = _FakeApiClient(httpx.Response(200, text=_SERVED))
        with patch("minitest_cli.commands.init_helpers.ApiClient", client):
            playbook, source = load_playbook(Settings())

        assert (playbook, source) == (_SERVED, "server")
        assert client.requested_path == PLAYBOOK_PATH

    @pytest.mark.parametrize(
        "response",
        [
            httpx.Response(401, text="unauthorized"),
            httpx.Response(200, text="  \n"),
            httpx.ConnectError("no route to host"),
        ],
        ids=["unauthenticated", "empty-body", "unreachable"],
    )
    def test_failures_fall_back_to_the_embedded_playbook(self, response):
        # `init` runs before the agent has authenticated and possibly offline, so it
        # must still print a usable playbook instead of erroring out.
        with patch("minitest_cli.commands.init_helpers.ApiClient", _FakeApiClient(response)):
            playbook, source = load_playbook(Settings())

        assert (playbook, source) == (FALLBACK_PLAYBOOK, "embedded")


class TestInitRendering:
    """`minitest init` emits the playbook in the right shape per context."""

    def test_agent_context_prints_raw_playbook_only(self, _served_playbook):
        with patch("minitest_cli.commands.init._is_agent_context", return_value=True):
            result = runner.invoke(app, ["init"])

        assert result.exit_code == 0
        assert result.stdout == _SERVED

    def test_human_context_adds_intro_around_playbook(self, _served_playbook):
        with patch("minitest_cli.commands.init._is_agent_context", return_value=False):
            result = runner.invoke(app, ["init"])

        assert result.exit_code == 0
        assert _HUMAN_MARKER in result.output
        assert "Served onboarding" in result.output
        assert result.output != _SERVED

    def test_json_mode_reports_the_playbook_and_its_source(self, _served_playbook):
        result = runner.invoke(app, ["--json", "init"])

        assert result.exit_code == 0
        assert json.loads(result.stdout) == {"playbook": _SERVED, "source": "server"}


class TestFallbackPlaybookContent:
    """The embedded copy must delegate, not re-invent the methodology."""

    def test_delegates_to_the_suite_design_workflow(self):
        assert "minitest-cli` skill" in FALLBACK_PLAYBOOK
        assert "reference/test-suite-design.md" in FALLBACK_PLAYBOOK
        assert "before reading any application code" in FALLBACK_PLAYBOOK
        assert "hard stops" in FALLBACK_PLAYBOOK

    def test_stops_before_build_and_run(self):
        # `init` designs the suite, then hands off to the web app's "Run tests"
        # button — it must NOT tell the agent to upload a build or start runs.
        assert "minitest build upload" not in FALLBACK_PLAYBOOK
        assert "minitest run" not in FALLBACK_PLAYBOOK
        assert "Run tests" in FALLBACK_PLAYBOOK

    def test_reuses_the_app_already_created_for_the_agent(self):
        assert "minitest apps list" in FALLBACK_PLAYBOOK
        assert "already been created" in FALLBACK_PLAYBOOK

    def test_routes_the_agent_to_the_capability_envelope(self):
        assert "minitest capabilities --platform" in FALLBACK_PLAYBOOK
