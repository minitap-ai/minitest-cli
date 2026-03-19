"""Async HTTP client with automatic auth and channel headers."""

from typing import Any

import httpx

from minitest_cli.core.auth import load_token
from minitest_cli.core.config import Settings

CHANNEL_HEADER = "X-Minitest-Channel"
CHANNEL_VALUE = "cli"
DEFAULT_TIMEOUT = 30.0
UPLOAD_TIMEOUT = 300.0  # 5 minutes for large file uploads


class ApiClient:
    """Wraps httpx.AsyncClient with auto-injected auth and channel headers.

    Usage::

        async with ApiClient(settings) as client:
            response = await client.get("/api/v1/apps")
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "ApiClient":
        token = load_token(self._settings)
        self._client = httpx.AsyncClient(
            base_url=self._settings.api_url,
            headers={
                "Authorization": f"Bearer {token}",
                CHANNEL_HEADER: CHANNEL_VALUE,
            },
            timeout=DEFAULT_TIMEOUT,
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        if self._client:
            await self._client.aclose()

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            msg = "ApiClient must be used as an async context manager"
            raise RuntimeError(msg)
        return self._client

    async def get(self, path: str, **kwargs: Any) -> httpx.Response:
        """Send a GET request."""
        return await self._ensure_client().get(path, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> httpx.Response:
        """Send a POST request."""
        return await self._ensure_client().post(path, **kwargs)

    async def patch(self, path: str, **kwargs: Any) -> httpx.Response:
        """Send a PATCH request."""
        return await self._ensure_client().patch(path, **kwargs)

    async def delete(self, path: str, **kwargs: Any) -> httpx.Response:
        """Send a DELETE request."""
        return await self._ensure_client().delete(path, **kwargs)

    async def upload_file(
        self,
        path: str,
        *,
        files: dict[str, Any],
        data: dict[str, str] | None = None,
        timeout: float = UPLOAD_TIMEOUT,
        **kwargs: Any,
    ) -> httpx.Response:
        """Send a POST request with multipart file upload and extended timeout."""
        client = self._ensure_client()
        return await client.post(
            path,
            files=files,
            data=data or {},
            timeout=timeout,
            **kwargs,
        )
