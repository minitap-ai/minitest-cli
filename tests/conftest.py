import os

import pytest


@pytest.fixture(autouse=True)
def _isolate_minitest_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the developer's MINITEST_* shell variables (e.g. MINITEST_APP_ID) out of tests."""
    for name in list(os.environ):
        if name.startswith("MINITEST_"):
            monkeypatch.delenv(name)
