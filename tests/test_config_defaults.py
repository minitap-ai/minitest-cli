from urllib.parse import urlparse

import pytest

from minitest_cli.core.config import (
    DEFAULT_API_URL,
    DEFAULT_APPS_MANAGER_URL,
    DEFAULT_CONDUCTOR_URL,
    DEFAULT_INTEGRATIONS_URL,
    DEFAULT_WEBAPP_URL,
)

PROD_SERVICE_URLS = [
    DEFAULT_API_URL,
    DEFAULT_APPS_MANAGER_URL,
    DEFAULT_CONDUCTOR_URL,
    DEFAULT_INTEGRATIONS_URL,
]


class TestProductionDefaults:
    @pytest.mark.parametrize("url", PROD_SERVICE_URLS)
    def test_service_default_points_at_a_production_host(self, url: str) -> None:
        host = urlparse(url).hostname or ""
        assert urlparse(url).scheme == "https"
        assert host.endswith(".app.minitap.ai"), host

    def test_integrations_default_is_the_resolvable_host(self) -> None:
        assert DEFAULT_INTEGRATIONS_URL == "https://integrations.app.minitap.ai"

    def test_webapp_default_is_production(self) -> None:
        assert DEFAULT_WEBAPP_URL == "https://app.minitap.ai"
