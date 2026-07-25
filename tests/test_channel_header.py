"""The X-Minitest-Channel header must honour MINITEST_CHANNEL for provenance."""

import asyncio
from unittest.mock import patch

import pytest

from minitest_cli.api.client import CHANNEL_HEADER, ApiClient
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
