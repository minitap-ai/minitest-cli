"""Tests for ApiClient — verifies the headers injected on every outgoing request."""

from __future__ import annotations

import asyncio

import httpx

from minitest_cli.api.client import CLIENT_HEADER, CLIENT_NAME, CHANNEL_HEADER, ApiClient
from minitest_cli.core.config import Settings


def _settings(tmp_path) -> Settings:
    return Settings(
        config_dir=tmp_path,
        token="test-token",
        supabase_url="https://test.supabase.co",
        supabase_publishable_key="test-key",
    )


class TestClientHeaders:
    def test_client_identification_header_is_injected(self, tmp_path) -> None:
        captured: list[httpx.Headers] = []

        async def _run() -> None:
            async with ApiClient(_settings(tmp_path), token_override="test-token") as client:
                assert client._client is not None
                captured.append(client._client.headers)

        asyncio.run(_run())

        assert len(captured) == 1
        assert captured[0][CLIENT_HEADER] == CLIENT_NAME

    def test_channel_header_is_injected(self, tmp_path) -> None:
        captured: list[httpx.Headers] = []

        async def _run() -> None:
            async with ApiClient(_settings(tmp_path), token_override="test-token") as client:
                assert client._client is not None
                captured.append(client._client.headers)

        asyncio.run(_run())

        assert len(captured) == 1
        assert CHANNEL_HEADER.lower() in {k.lower() for k in captured[0].keys()}
