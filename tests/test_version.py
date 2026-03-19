"""Smoke test for package version."""

from minitest_cli import __version__


class TestVersion:
    def test_version_is_set(self) -> None:
        assert __version__
        assert isinstance(__version__, str)
        # Version comes from pyproject.toml via importlib.metadata
        parts = __version__.split(".")
        assert len(parts) >= 2, "Version should be semver-like (e.g. 0.1.0)"
