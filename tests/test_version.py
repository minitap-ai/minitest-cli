"""Smoke test for package version."""

from minitest_cli import __version__


class TestVersion:
    def test_version_is_set(self) -> None:
        assert __version__ == "0.1.0"
