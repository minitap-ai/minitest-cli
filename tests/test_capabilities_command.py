from typer.testing import CliRunner

from minitest_cli.main import app

runner = CliRunner()


def test_unknown_platform_is_rejected_before_any_network_call():
    result = runner.invoke(app, ["capabilities", "--platform", "windows"])

    assert result.exit_code != 0
    assert "android, ios, web" in result.output
