"""Both console scripts run the CLI, and a foreign `minitest` earlier in PATH is reported."""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from click import unstyle
from typer.testing import CliRunner

from minitest_cli import __version__
from minitest_cli.main import app
from minitest_cli.utils.invoked_name import as_invoked
from minitest_cli.utils.path_clash import PathClash, find_path_clash, warn_if_shadowed

VENV_BIN = Path(sys.executable).parent
RUBY_MINITEST = '#!/bin/sh\necho "minitest 6.0.0"\nexit 0\n'


def _script(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text(body)
    path.chmod(0o755)


def _path_with_first(monkeypatch: pytest.MonkeyPatch, *dirs: Path) -> None:
    monkeypatch.setenv("PATH", os.pathsep.join([*map(str, dirs), os.environ["PATH"]]))


class TestEntryPoints:
    @pytest.mark.parametrize("name", ["minitest", "minitest-cli"])
    def test_entry_point_runs_the_cli(self, name: str) -> None:
        script = shutil.which(name, path=str(VENV_BIN))
        assert script, f"{name} console script is not installed in {VENV_BIN}"

        version = subprocess.run([script, "--version"], capture_output=True, text=True)
        usage = subprocess.run([script, "auth", "--help"], capture_output=True, text=True)

        assert version.returncode == 0
        assert version.stdout.strip() == f"minitest-cli {__version__}"
        assert usage.returncode == 0
        assert f"Usage: {name} auth" in unstyle(usage.stdout)


@pytest.mark.skipif(sys.platform == "win32", reason="fake executables are shell scripts")
class TestPathClash:
    def test_find_path_clash_reports_ruby_minitest_first_in_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _script(tmp_path, "minitest", RUBY_MINITEST)
        _path_with_first(monkeypatch, tmp_path, VENV_BIN)

        assert find_path_clash() == PathClash(
            path=str(tmp_path / "minitest"), version_output="minitest 6.0.0"
        )

    def test_find_path_clash_accepts_this_cli_first_in_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _path_with_first(monkeypatch, VENV_BIN)

        assert find_path_clash() is None

    def test_find_path_clash_reports_silent_program(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _script(tmp_path, "minitest", "#!/bin/sh\nexit 0\n")
        _path_with_first(monkeypatch, tmp_path)

        assert find_path_clash() == PathClash(path=str(tmp_path / "minitest"), version_output="")

    def test_warn_if_shadowed_names_the_fix(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _script(tmp_path, "minitest", RUBY_MINITEST)
        _path_with_first(monkeypatch, tmp_path, VENV_BIN)
        monkeypatch.setenv("COLUMNS", "500")

        warn_if_shadowed()

        warning = unstyle(capsys.readouterr().err)
        assert str(tmp_path / "minitest") in warning
        assert "Run `minitest-cli` instead" in warning
        assert f"put {VENV_BIN} first in PATH" in warning


class TestHintsNameTheInvokedCommand:
    @pytest.mark.parametrize(
        ("prog_name", "hint"),
        [
            ("minitest-cli", "`minitest-cli upgrade` still updates by hand"),
            ("minitest", "`minitest upgrade` still updates by hand"),
        ],
    )
    def test_upgrade_auto_off_hint(
        self, prog_name: str, hint: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MINITEST_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("COLUMNS", "500")
        monkeypatch.setattr(sys, "argv", [f"/home/me/.local/bin/{prog_name}"])

        with patch("minitest_cli.main.check_for_updates"):
            result = CliRunner().invoke(app, ["upgrade", "auto", "off"])

        assert result.exit_code == 0, result.output
        assert hint in unstyle(result.stderr)

    def test_not_authenticated_hint_under_minitest_cli(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MINITEST_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("COLUMNS", "500")
        monkeypatch.setattr(sys, "argv", ["minitest-cli.exe"])

        with patch("minitest_cli.main.check_for_updates"):
            result = CliRunner().invoke(app, ["auth", "status"])

        assert result.exit_code == 2
        assert "Run `minitest-cli auth login` or set MINITEST_TOKEN" in unstyle(result.stderr)

    @pytest.mark.parametrize(
        "text",
        ["minitest-cli 1.0.0", "Ruby's minitest 6.0.0", "~/.minitest/auth.log", "the minitest CLI"],
    )
    def test_as_invoked_leaves_non_commands_alone(
        self, text: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sys, "argv", ["minitest-cli"])

        assert as_invoked(text) == text
