"""The X-Minitest-Channel header must honour MINITEST_CHANNEL for provenance."""

import asyncio
from unittest.mock import patch

import pytest

from minitest_cli import __version__
from minitest_cli.api.apps_manager_client import AppsManagerClient
from minitest_cli.api.client import CHANNEL_HEADER, CLI_HEADER, CLI_HEADER_VALUE, ApiClient
from minitest_cli.core.config import Settings


class TestChannelHeader:
    @pytest.mark.parametrize(
        ("settings", "expected"),
        [
            (Settings(), "cli"),
            (Settings(channel="chat_edited"), "chat_edited"),
        ],
    )
    def test_api_client_sends_configured_channel(self, settings, expected):
        async def _headers() -> str:
            async with ApiClient(settings) as client:
                return client._ensure_client().headers[CHANNEL_HEADER]

        with patch("minitest_cli.api.client.load_token", return_value="tok"):
            assert asyncio.run(_headers()) == expected

    def test_channel_env_var_overrides_default(self, monkeypatch):
        monkeypatch.setenv("MINITEST_CHANNEL", "chat_edited")
        assert Settings().channel == "chat_edited"


class TestCliVersionHeader:
    def test_api_client_sends_cli_name_and_version(self):
        async def _headers() -> str:
            async with ApiClient(Settings()) as client:
                return client._ensure_client().headers[CLI_HEADER]

        with patch("minitest_cli.api.client.load_token", return_value="tok"):
            assert asyncio.run(_headers()) == f"minitest/{__version__}"

    def test_apps_manager_client_sends_cli_name_and_version(self):
        async def _headers() -> str:
            async with AppsManagerClient(Settings()) as client:
                return client._ensure_client().headers[CLI_HEADER]

        with patch("minitest_cli.api.apps_manager_client.load_token", return_value="tok"):
            assert asyncio.run(_headers()) == f"minitest/{__version__}"

    def test_header_value_matches_version_flag(self):
        assert CLI_HEADER_VALUE == f"minitest/{__version__}"
