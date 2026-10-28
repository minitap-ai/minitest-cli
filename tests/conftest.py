import os

import pytest


@pytest.fixture(autouse=True)
def _isolate_minitest_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the developer's MINITEST_* shell variables (e.g. MINITEST_APP_ID) out of tests."""
    for name in list(os.environ):
        if name.startswith("MINITEST_"):
            monkeypatch.delenv(name)
    # Never upgrade the developer's real CLI from a test; auto-update tests opt back in.
    monkeypatch.setenv("MINITEST_NO_AUTO_UPDATE", "1")


@pytest.fixture(autouse=True)
def _app_names_resolve_to_themselves(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Most tests target fake ids like "app-1"; keep them off the name lookup.

    Tests of the lookup itself opt back in with ``@pytest.mark.real_app_lookup``.
    """
    if request.node.get_closest_marker("real_app_lookup"):
        return
    monkeypatch.setattr(
        "minitest_cli.core.app_context._app_id_by_name", lambda _settings, name: name
    )
